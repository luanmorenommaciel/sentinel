package chstore

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/ClickHouse/clickhouse-go/v2"
	"sentinel/collector/internal/model"
)

// ErrBufferFull is returned by the Send* methods when the in-memory buffer is
// full — the flush goroutines are not draining fast enough (ClickHouse slow or
// down). The gRPC handlers map it to codes.ResourceExhausted (EP3.1).
var ErrBufferFull = errors.New("chstore: buffer full")

type Store struct {
	conn          clickhouse.Conn
	logger        *slog.Logger
	target        string
	spanCh        chan model.Span
	logCh         chan model.Log
	metricCh      chan model.Metric
	spanSendMu    sync.Mutex
	logSendMu     sync.Mutex
	metricSendMu  sync.Mutex
	batchSize     int
	flushInterval time.Duration
	wg            sync.WaitGroup
}

// New opens a ClickHouse connection and prepares the buffered store. target selects
// the hot-path destination (ADR-0009): "bronze" writes sentinel.*, anything else
// ("normalized") writes the opt-in default.* schema + otel_metrics_1m MV.
func New(dsn, target string, batchSize int, flushInterval time.Duration, logger *slog.Logger) (*Store, error) {
	if batchSize <= 0 {
		return nil, fmt.Errorf("chstore: batch size must be > 0, got %d", batchSize)
	}
	if flushInterval <= 0 {
		return nil, fmt.Errorf("chstore: flush interval must be > 0, got %s", flushInterval)
	}
	if target != "" && target != "bronze" && target != "normalized" {
		return nil, fmt.Errorf("chstore: unsupported target %q", target)
	}
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
		target:        target,
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

// SendSpan/SendLog/SendMetric enqueue non-blockingly, returning ErrBufferFull
// when the channel is saturated (flush not keeping up) so the caller can reject
// the export rather than block or silently succeed (EP3.1).
func (s *Store) SendSpans(spans []model.Span) error {
	return trySendBatch(s.spanCh, spans, &s.spanSendMu)
}

func (s *Store) SendLogs(logs []model.Log) error {
	return trySendBatch(s.logCh, logs, &s.logSendMu)
}

func (s *Store) SendMetrics(metrics []model.Metric) error {
	return trySendBatch(s.metricCh, metrics, &s.metricSendMu)
}

// trySendBatch serializes producers and reserves capacity for the complete
// request before sending any item. Consumers may free additional slots while
// the loop runs, so after this check the request cannot be partially accepted.
func trySendBatch[T any](ch chan T, items []T, mu *sync.Mutex) error {
	if len(items) == 0 {
		return nil
	}
	mu.Lock()
	defer mu.Unlock()
	if len(items) > cap(ch)-len(ch) {
		return ErrBufferFull
	}
	for _, item := range items {
		ch <- item
	}
	return nil
}

// bronze reports whether the hot path writes sentinel.* (ADR-0009). Any value other
// than "bronze" selects the opt-in normalized default.* schema.
func (s *Store) bronze() bool { return s.target == "" || s.target == "bronze" }

func (s *Store) flushSpans(ctx context.Context) {
	defer s.wg.Done()
	insert := s.insertSpans
	if s.bronze() {
		insert = s.insertBronzeTraces
	}
	flushLoop(ctx, s.spanCh, s.batchSize, s.flushInterval, s.logger, "spans", insert)
}

func (s *Store) flushLogs(ctx context.Context) {
	defer s.wg.Done()
	insert := s.insertLogs
	if s.bronze() {
		insert = s.insertBronzeLogs
	}
	flushLoop(ctx, s.logCh, s.batchSize, s.flushInterval, s.logger, "logs", insert)
}

func (s *Store) flushMetrics(ctx context.Context) {
	defer s.wg.Done()
	insert := s.insertMetrics
	if s.bronze() {
		insert = s.insertBronzeMetricsSplit
	}
	flushLoop(ctx, s.metricCh, s.batchSize, s.flushInterval, s.logger, "metrics", insert)
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

	flush := func(flushCtx context.Context) {
		if len(batch) == 0 {
			return
		}
		count := len(batch)
		var err error
	attempts:
		for attempt := 0; attempt < 3; attempt++ {
			err = insert(flushCtx, batch)
			if err == nil {
				flushTotal.WithLabelValues(signal, "success").Inc()
				flushSize.WithLabelValues(signal).Observe(float64(count))
				storedSignals.WithLabelValues(signal, "persisted").Add(float64(count))
				logger.Debug("batch flushed", "signal", signal, "count", count)
				batch = batch[:0]
				return
			}
			delay := time.Duration(100*(1<<attempt)) * time.Millisecond
			logger.Warn("batch flush failed, retrying",
				"signal", signal, "attempt", attempt+1, "delay_ms", delay.Milliseconds(), "error", err)
			timer := time.NewTimer(delay + retryJitter(delay))
			select {
			case <-timer.C:
			case <-flushCtx.Done():
				timer.Stop()
				break attempts
			}
		}
		flushTotal.WithLabelValues(signal, "failure").Inc()
		insertErrors.WithLabelValues(signal).Inc()
		storedSignals.WithLabelValues(signal, "dropped").Add(float64(count))
		logger.Error("batch flush failed after 3 attempts, dropping",
			"signal", signal, "count", count, "error", err)
		batch = batch[:0]
	}

	for {
		select {
		case item, ok := <-ch:
			if !ok {
				flush(ctx)
				return
			}
			batch = append(batch, item)
			if len(batch) >= batchSize {
				flush(ctx)
			}
		case <-ticker.C:
			flush(ctx)
		case <-ctx.Done():
			// drain remaining items enqueued before context cancel
			for len(ch) > 0 {
				batch = append(batch, <-ch)
			}
			drainCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			flush(drainCtx)
			cancel()
			return
		}
	}
}

func retryJitter(base time.Duration) time.Duration {
	span := base / 2
	if span <= 0 {
		return 0
	}
	return time.Duration(time.Now().UnixNano() % int64(span))
}
