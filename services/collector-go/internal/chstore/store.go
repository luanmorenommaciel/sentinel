package chstore

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/ClickHouse/clickhouse-go/v2"
	"sentinel/collector/internal/model"
)

type Store struct {
	conn          clickhouse.Conn
	logger        *slog.Logger
	spanCh        chan model.Span
	logCh         chan model.Log
	metricCh      chan model.Metric
	batchSize     int
	flushInterval time.Duration
	wg            sync.WaitGroup
}

func New(dsn string, batchSize int, flushInterval time.Duration, logger *slog.Logger) (*Store, error) {
	opts, err := clickhouse.ParseDSN(dsn)
	if err != nil {
		return nil, fmt.Errorf("chstore: parse DSN: %w", err)
	}

	conn, err := clickhouse.Open(opts)
	if err != nil {
		return nil, fmt.Errorf("chstore: open: %w", err)
	}
	if err := conn.Ping(context.Background()); err != nil {
		return nil, fmt.Errorf("chstore: ping: %w", err)
	}

	return &Store{
		conn:          conn,
		logger:        logger,
		spanCh:        make(chan model.Span, batchSize*4),
		logCh:         make(chan model.Log, batchSize*4),
		metricCh:      make(chan model.Metric, batchSize*4),
		batchSize:     batchSize,
		flushInterval: flushInterval,
	}, nil
}

// Start launches the three background flush goroutines.
func (s *Store) Start(ctx context.Context) {
	s.wg.Add(3)
	go s.flushSpans(ctx)
	go s.flushLogs(ctx)
	go s.flushMetrics(ctx)
}

// Close waits for all flush goroutines to drain then closes the connection.
func (s *Store) Close() error {
	s.wg.Wait()
	return s.conn.Close()
}

// Ready returns nil when the ClickHouse connection is alive.
func (s *Store) Ready(ctx context.Context) error {
	return s.conn.Ping(ctx)
}

// Conn exposes the underlying ClickHouse connection for integration tests.
func (s *Store) Conn() clickhouse.Conn { return s.conn }

func (s *Store) SendSpan(span model.Span)   { s.spanCh <- span }
func (s *Store) SendLog(log model.Log)       { s.logCh <- log }
func (s *Store) SendMetric(m model.Metric)   { s.metricCh <- m }

func (s *Store) flushSpans(ctx context.Context) {
	defer s.wg.Done()
	flushLoop(ctx, s.spanCh, s.batchSize, s.flushInterval, s.logger, "spans", s.insertSpans)
}

func (s *Store) flushLogs(ctx context.Context) {
	defer s.wg.Done()
	flushLoop(ctx, s.logCh, s.batchSize, s.flushInterval, s.logger, "logs", s.insertLogs)
}

func (s *Store) flushMetrics(ctx context.Context) {
	defer s.wg.Done()
	flushLoop(ctx, s.metricCh, s.batchSize, s.flushInterval, s.logger, "metrics", s.insertMetrics)
}

func flushLoop[T any](
	ctx context.Context,
	ch <-chan T,
	batchSize int,
	interval time.Duration,
	logger *slog.Logger,
	signal string,
	insert func(context.Context, []T) error,
) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	batch := make([]T, 0, batchSize)

	flush := func() {
		if len(batch) == 0 {
			return
		}
		count := len(batch)
		var err error
		for attempt := 0; attempt < 3; attempt++ {
			err = insert(ctx, batch)
			if err == nil {
				flushTotal.WithLabelValues(signal, "success").Inc()
				flushSize.WithLabelValues(signal).Observe(float64(count))
				logger.Debug("batch flushed", "signal", signal, "count", count)
				batch = batch[:0]
				return
			}
			delay := time.Duration(100*(1<<attempt)) * time.Millisecond
			logger.Warn("batch flush failed, retrying",
				"signal", signal, "attempt", attempt+1, "delay_ms", delay.Milliseconds(), "error", err)
			time.Sleep(delay)
		}
		flushTotal.WithLabelValues(signal, "failure").Inc()
		insertErrors.WithLabelValues(signal).Inc()
		logger.Error("batch flush failed after 3 attempts, dropping",
			"signal", signal, "count", count, "error", err)
		batch = batch[:0]
	}

	for {
		select {
		case item, ok := <-ch:
			if !ok {
				flush()
				return
			}
			batch = append(batch, item)
			if len(batch) >= batchSize {
				flush()
			}
		case <-ticker.C:
			flush()
		case <-ctx.Done():
			// drain remaining items enqueued before context cancel
			for len(ch) > 0 {
				batch = append(batch, <-ch)
			}
			flush()
			return
		}
	}
}
