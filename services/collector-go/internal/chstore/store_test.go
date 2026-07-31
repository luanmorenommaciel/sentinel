package chstore

import (
	"sync"
	"testing"
)

func TestTrySendBatchRejectsWithoutPartialEnqueue(t *testing.T) {
	ch := make(chan int, 3)
	ch <- 1
	var mu sync.Mutex

	if err := trySendBatch(ch, []int{2, 3, 4}, &mu); err != ErrBufferFull {
		t.Fatalf("got %v, want ErrBufferFull", err)
	}
	if got := len(ch); got != 1 {
		t.Fatalf("partially enqueued batch: channel length=%d, want 1", got)
	}
}

func TestTrySendBatchAcceptsWholeBatch(t *testing.T) {
	ch := make(chan int, 3)
	var mu sync.Mutex
	if err := trySendBatch(ch, []int{1, 2, 3}, &mu); err != nil {
		t.Fatalf("trySendBatch: %v", err)
	}
	if got := len(ch); got != 3 {
		t.Fatalf("channel length=%d, want 3", got)
	}
}
