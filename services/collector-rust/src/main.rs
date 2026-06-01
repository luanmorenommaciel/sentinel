// Sentinel OTel Collector — Rust skeleton.
//
// Status: scaffold only. Does not yet bind to :4317 or write to ClickHouse.
// The point of this file is to anchor the Cargo manifest and CI gates; the
// receiver + exporter loop lands once ADR-0004 is accepted.
//
// See: docs/adr/0004-collector-implementation-language.md
//      docs/research/rust-otel-collector.md

use anyhow::Result;
use tracing::info;
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> Result<()> {
    init_tracing();

    info!(
        version = env!("CARGO_PKG_VERSION"),
        "sentinel-collector starting (scaffold — no receiver bound yet)"
    );

    // Next: bind tonic OTLP gRPC server on :4317.
    // Reference shape:
    //
    //   let addr = "0.0.0.0:4317".parse()?;
    //   let trace_svc = TraceServiceServer::new(SentinelTraceReceiver::default());
    //   tonic::transport::Server::builder()
    //       .add_service(trace_svc)
    //       .serve(addr)
    //       .await?;

    info!("scaffold exiting cleanly");
    Ok(())
}

fn init_tracing() {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")))
        .json()
        .init();
}

#[cfg(test)]
mod tests {
    #[test]
    fn scaffold_compiles() {
        assert!(true, "if this doesn't pass we have bigger problems");
    }
}
