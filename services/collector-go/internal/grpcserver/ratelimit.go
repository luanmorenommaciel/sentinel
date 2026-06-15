package grpcserver

import (
	"context"

	"golang.org/x/time/rate"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// RateLimitInterceptor returns a unary server interceptor that limits requests
// to rps per second using a token bucket. Pass rps=0 to disable rate limiting.
func RateLimitInterceptor(rps int) grpc.UnaryServerInterceptor {
	if rps <= 0 {
		return func(ctx context.Context, req any, _ *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
			return handler(ctx, req)
		}
	}
	limiter := rate.NewLimiter(rate.Limit(rps), rps)
	return func(ctx context.Context, req any, _ *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
		if !limiter.Allow() {
			return nil, status.Errorf(codes.ResourceExhausted, "rate limit exceeded (%d rps)", rps)
		}
		return handler(ctx, req)
	}
}
