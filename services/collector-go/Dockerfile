FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /bin/collector ./cmd/collector

FROM alpine:3.20
RUN apk add --no-cache ca-certificates tzdata wget
COPY --from=builder /bin/collector /bin/collector
EXPOSE 4317 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s \
    CMD wget -qO- http://localhost:8080/health || exit 1
ENTRYPOINT ["/bin/collector"]
