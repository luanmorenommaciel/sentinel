//! `/metrics` HTTP server — EP3.2.
//!
//! Serves the [`crate::metrics::Metrics`] registry in the Prometheus text
//! exposition format, mirroring the Go collector's
//! `internal/httpserver.Server` (`promhttp.Handler()` mounted at
//! `/metrics`).
//!
//! # Why a hand-rolled accept loop instead of a web framework
//!
//! `hyper` 1.x + `hyper-util`'s `TokioIo` + `http-body-util`'s `Full` body
//! are already resolved in `Cargo.lock` as transitive dependencies of
//! `tonic` — this module adds no new crate to the dependency tree, only
//! extra feature flags on crates already present. A framework (axum, warp)
//! would pull in a materially larger dep graph for one route. See
//! `RUST_PROJECT_STANDARDS.md` on keeping the musl/distroless image's
//! dependency surface minimal.
//!
//! # Shape
//!
//! Mirrors `crate::grpc`'s `serve` / `serve_with_listener` split: `serve`
//! binds `addr` itself; `serve_with_listener` accepts an already-bound
//! [`TcpListener`] so tests can bind an ephemeral port (`127.0.0.1:0`)
//! without a bind race. Both run until `shutdown` resolves.

use std::convert::Infallible;
use std::net::SocketAddr;
use std::sync::Arc;

use bytes::Bytes;
use http_body_util::Full;
use hyper::body::Incoming;
use hyper::server::conn::http1;
use hyper::service::service_fn;
use hyper::{Request, Response, StatusCode};
use hyper_util::rt::TokioIo;
use thiserror::Error;
use tokio::net::TcpListener;
use tracing::{debug, error, info};

use crate::metrics::Metrics;

/// Errors starting the `/metrics` HTTP server.
#[derive(Debug, Error)]
pub enum MetricsServerError {
    /// The listen address could not be bound (only returned from [`serve`];
    /// [`serve_with_listener`] takes an already-bound listener).
    #[error("binding metrics listener on {addr}: {source}")]
    Bind {
        addr: SocketAddr,
        #[source]
        source: std::io::Error,
    },
}

/// `text/plain; version=0.0.4` — the Prometheus exposition format's content
/// type, as served by `promhttp.Handler()` on the Go side.
const PROMETHEUS_CONTENT_TYPE: &str = "text/plain; version=0.0.4; charset=utf-8";

/// Build the HTTP response for one request: `/metrics` renders the
/// registry; anything else is `404`.
async fn handle(
    req: Request<Incoming>,
    metrics: Arc<Metrics>,
) -> Result<Response<Full<Bytes>>, Infallible> {
    if req.uri().path() != "/metrics" {
        let mut resp = Response::new(Full::new(Bytes::from_static(b"not found\n")));
        *resp.status_mut() = StatusCode::NOT_FOUND;
        return Ok(resp);
    }

    match metrics.render() {
        Ok(body) => {
            let mut resp = Response::new(Full::new(Bytes::from(body)));
            resp.headers_mut().insert(
                hyper::header::CONTENT_TYPE,
                hyper::header::HeaderValue::from_static(PROMETHEUS_CONTENT_TYPE),
            );
            Ok(resp)
        }
        Err(err) => {
            error!(error = %err, "rendering /metrics failed");
            let mut resp = Response::new(Full::new(Bytes::from_static(
                b"internal error rendering metrics\n",
            )));
            *resp.status_mut() = StatusCode::INTERNAL_SERVER_ERROR;
            Ok(resp)
        }
    }
}

/// Serve `/metrics` on an already-bound [`TcpListener`] until `shutdown`
/// resolves.
///
/// Each accepted connection is handled on its own spawned task; a
/// connection-level error (e.g. the client disconnecting mid-response) is
/// logged at `debug` and does not affect other connections or the server
/// loop.
///
/// # Errors
///
/// This function itself does not fail — connection errors are logged, not
/// propagated — but returns `Result` for symmetry with `crate::grpc`'s
/// serve functions and to leave room for a future fatal-accept-error path.
pub async fn serve_with_listener(
    listener: TcpListener,
    metrics: Arc<Metrics>,
    shutdown: impl std::future::Future<Output = ()>,
) -> Result<(), MetricsServerError> {
    tokio::pin!(shutdown);

    loop {
        tokio::select! {
            biased;

            () = &mut shutdown => {
                return Ok(());
            }

            accepted = listener.accept() => {
                let (stream, peer) = match accepted {
                    Ok(pair) => pair,
                    Err(err) => {
                        debug!(error = %err, "metrics server: accept failed");
                        continue;
                    }
                };
                let io = TokioIo::new(stream);
                let metrics = Arc::clone(&metrics);
                tokio::spawn(async move {
                    let service = service_fn(move |req| handle(req, Arc::clone(&metrics)));
                    if let Err(err) = http1::Builder::new().serve_connection(io, service).await {
                        debug!(error = %err, %peer, "metrics server: connection error");
                    }
                });
            }
        }
    }
}

/// Bind `addr` and serve `/metrics` until `shutdown` resolves.
///
/// # Errors
///
/// Returns [`MetricsServerError::Bind`] if `addr` cannot be bound.
pub async fn serve(
    addr: SocketAddr,
    metrics: Arc<Metrics>,
    shutdown: impl std::future::Future<Output = ()>,
) -> Result<(), MetricsServerError> {
    let listener = TcpListener::bind(addr)
        .await
        .map_err(|source| MetricsServerError::Bind { addr, source })?;
    info!(%addr, "Prometheus /metrics server listening");
    serve_with_listener(listener, metrics, shutdown).await
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use std::time::Duration;

    use tokio::sync::oneshot;

    use super::*;

    async fn start_server() -> (
        SocketAddr,
        Arc<Metrics>,
        oneshot::Sender<()>,
        tokio::task::JoinHandle<()>,
    ) {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let metrics = Metrics::new_shared().expect("registers cleanly");
        let metrics_for_server = Arc::clone(&metrics);
        let (tx, rx) = oneshot::channel::<()>();

        let handle = tokio::spawn(async move {
            let shutdown = async {
                let _ = rx.await;
            };
            serve_with_listener(listener, metrics_for_server, shutdown)
                .await
                .expect("server runs cleanly");
        });

        tokio::time::sleep(Duration::from_millis(50)).await;
        (addr, metrics, tx, handle)
    }

    #[tokio::test]
    async fn metrics_endpoint_serves_prometheus_text_format() {
        let (addr, metrics, shutdown, handle) = start_server().await;
        metrics
            .signals_ingested_total
            .with_label_values(&["trace"])
            .inc();

        let response = reqwest_like_get(addr, "/metrics").await;
        assert_eq!(response.0, 200);
        assert!(response.1.contains("sentinel_signals_ingested_total"));
        assert!(response.1.contains(r#"signal="trace""#));

        let _ = shutdown.send(());
        handle.await.unwrap();
    }

    #[tokio::test]
    async fn unknown_path_returns_404() {
        let (addr, _metrics, shutdown, handle) = start_server().await;

        let response = reqwest_like_get(addr, "/nope").await;
        assert_eq!(response.0, 404);

        let _ = shutdown.send(());
        handle.await.unwrap();
    }

    /// Minimal hand-rolled HTTP/1.1 GET — avoids adding a test-only HTTP
    /// client dependency for two assertions. Returns `(status_code, body)`.
    async fn reqwest_like_get(addr: SocketAddr, path: &str) -> (u16, String) {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        use tokio::net::TcpStream;

        let mut stream = TcpStream::connect(addr).await.unwrap();
        let request =
            format!("GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n");
        stream.write_all(request.as_bytes()).await.unwrap();
        // Do NOT half-close the write side here — the server (hyper) honours
        // `Connection: close` and closes the socket itself once the
        // response is written; that close is what unblocks `read_to_end`
        // below. Half-closing from the client side too early raced the
        // server's read of the still-in-flight request bytes and produced
        // `hyper::Error(IncompleteMessage)`.
        let mut raw = Vec::new();
        stream.read_to_end(&mut raw).await.unwrap();
        let raw = String::from_utf8_lossy(&raw);

        let status_line = raw.lines().next().unwrap_or_default();
        let status: u16 = status_line
            .split_whitespace()
            .nth(1)
            .and_then(|s| s.parse().ok())
            .unwrap_or(0);
        let body = raw.split("\r\n\r\n").nth(1).unwrap_or_default().to_string();
        (status, body)
    }
}
