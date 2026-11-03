//! Exercise OS shutdown signals against the actual collector process (#45).
//! Live tests additionally prove that an acknowledged partial batch is drained.

#![cfg(unix)]
#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Duration;

use opentelemetry_proto::tonic::collector::logs::v1::{
    logs_service_client::LogsServiceClient, ExportLogsServiceRequest,
};
use opentelemetry_proto::tonic::common::v1::{any_value, AnyValue};
use opentelemetry_proto::tonic::logs::v1::{LogRecord, ResourceLogs, ScopeLogs};

mod support;

static NEXT_PROCESS: AtomicUsize = AtomicUsize::new(0);

struct CollectorProcess {
    child: Child,
    config: PathBuf,
    endpoint: String,
}

impl CollectorProcess {
    fn start(clickhouse_url: Option<&str>) -> Self {
        let grpc_listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let metrics_listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let grpc_port = grpc_listener.local_addr().unwrap().port();
        let metrics_port = metrics_listener.local_addr().unwrap().port();
        let config = std::env::temp_dir().join(format!(
            "sentinel-shutdown-{}-{}.yaml",
            std::process::id(),
            NEXT_PROCESS.fetch_add(1, Ordering::Relaxed)
        ));
        let mut yaml = format!(
            "grpc:\n  listen: '127.0.0.1:{grpc_port}'\nmetrics:\n  listen: '127.0.0.1:{metrics_port}'\ncontract:\n  grpc_validation: off\n"
        );
        if let Some(url) = clickhouse_url {
            // Through the helper, so this process gets the same credential the
            // verifying client uses. A mismatch here would not fail the test
            // loudly — the flush would simply write nothing and the SELECT would
            // come back empty, which reads as a shutdown defect.
            yaml.push_str(&support::clickhouse_config_block(
                url,
                "bronze",
                "  batch_size: 1000\n  flush_interval_ms: 60000\n",
            ));
        }
        std::fs::write(&config, yaml).expect("write process configuration");
        drop(grpc_listener);
        drop(metrics_listener);
        let child = Command::new(env!("CARGO_BIN_EXE_sentinel-collector"))
            .arg(&config)
            .env_remove("CLICKHOUSE_URL")
            .env_remove("METRICS_PORT")
            .env_remove("BATCH_SIZE")
            .env_remove("FLUSH_INTERVAL_MS")
            .stdout(Stdio::null())
            .spawn()
            .expect("start collector binary");
        Self {
            child,
            config,
            endpoint: format!("http://127.0.0.1:{grpc_port}"),
        }
    }

    async fn ready(&mut self) -> LogsServiceClient<tonic::transport::Channel> {
        tokio::time::timeout(Duration::from_secs(5), async {
            loop {
                assert!(
                    self.child.try_wait().unwrap().is_none(),
                    "collector exited at startup"
                );
                if let Ok(client) = LogsServiceClient::connect(self.endpoint.clone()).await {
                    // Let the buffer's immediate first timer tick pass before enqueuing.
                    tokio::time::sleep(Duration::from_millis(100)).await;
                    return client;
                }
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("collector accepts gRPC connections")
    }

    async fn stop(&mut self, signal: &str) {
        let sent = Command::new("kill")
            .arg(format!("-{signal}"))
            .arg(self.child.id().to_string())
            .status()
            .expect("send shutdown signal");
        assert!(sent.success());
        let status = tokio::time::timeout(Duration::from_secs(3), async {
            loop {
                if let Some(status) = self.child.try_wait().unwrap() {
                    return status;
                }
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .unwrap_or_else(|_| panic!("collector did not exit within 3 seconds after SIG{signal}"));
        assert!(
            status.success(),
            "SIG{signal} should exit successfully: {status}"
        );
    }
}

impl Drop for CollectorProcess {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
        let _ = std::fs::remove_file(&self.config);
    }
}

#[tokio::test]
async fn sigterm_stops_collector_cleanly() {
    let mut collector = CollectorProcess::start(None);
    let _client = collector.ready().await;
    collector.stop("TERM").await;
}

#[tokio::test]
async fn sigint_stops_collector_cleanly() {
    let mut collector = CollectorProcess::start(None);
    let _client = collector.ready().await;
    collector.stop("INT").await;
}

async fn buffered_log_is_flushed(signal: &str) {
    let url = support::clickhouse_url();
    let verify = support::client("bronze");
    let mut collector = CollectorProcess::start(Some(&url));
    let mut client = collector.ready().await;
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let body = format!("shutdown-{}-{nonce}-{signal}", collector.child.id());
    client
        .export(ExportLogsServiceRequest {
            resource_logs: vec![ResourceLogs {
                scope_logs: vec![ScopeLogs {
                    log_records: vec![LogRecord {
                        time_unix_nano: 1_900_000_000_000_000_000,
                        severity_number: 9,
                        severity_text: "INFO".to_string(),
                        body: Some(AnyValue {
                            value: Some(any_value::Value::StringValue(body.clone())),
                        }),
                        ..Default::default()
                    }],
                    ..Default::default()
                }],
                ..Default::default()
            }],
        })
        .await
        .expect("collector acknowledges buffered log");
    drop(client);

    let query = "SELECT count() FROM otel_logs WHERE Body = ?";
    let before: u64 = verify.query(query).bind(&body).fetch_one().await.unwrap();
    assert_eq!(before, 0, "log must still be buffered before shutdown");

    collector.stop(signal).await;
    let after: u64 = verify.query(query).bind(&body).fetch_one().await.unwrap();
    assert_eq!(after, 1, "shutdown must persist the acknowledged log");
}

#[tokio::test]
#[ignore = "requires a live ClickHouse instance — run with --ignored"]
async fn sigterm_flushes_acknowledged_buffer_to_clickhouse() {
    buffered_log_is_flushed("TERM").await;
}

#[tokio::test]
#[ignore = "requires a live ClickHouse instance — run with --ignored"]
async fn sigint_flushes_acknowledged_buffer_to_clickhouse() {
    buffered_log_is_flushed("INT").await;
}
