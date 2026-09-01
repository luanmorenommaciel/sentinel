"""The declared topology, read from the producer's own config rather than redrawn."""
from __future__ import annotations

from flow_ui import topology


def test_the_graph_comes_from_the_generators_own_config():
    g = topology.service_graph()
    assert g["source"] and g["source"].endswith("topology/default.yaml")
    assert g["version"] == "1.0.0"


def test_every_component_becomes_a_node():
    assert len(topology.service_graph()["nodes"]) == 7


def test_edges_point_the_way_data_flows_not_the_way_the_yaml_reads():
    """`depends_on: [a]` on b means a produces what b consumes, so the edge is a → b.
    Reading it the other way would draw every arrow backwards — the kind of mistake a
    diagram never announces."""
    g = topology.service_graph()
    edges = {(e["from"], e["to"]) for e in g["edges"]}
    assert ("messaging.ingestion_topic", "compute.spark_batch") in edges
    assert ("compute.spark_batch", "messaging.ingestion_topic") not in edges
    assert len(edges) == 8


def test_roots_are_the_components_that_depend_on_nothing():
    roots = {n["service"] for n in topology.service_graph()["nodes"] if n["roots"]}
    assert roots == {"pubsub-ingestion-topic", "cloud-composer-etl"}


def test_a_missing_config_degrades_to_an_empty_graph(monkeypatch):
    """The page must still render where the generator config is not mounted."""
    monkeypatch.setattr(topology, "_CANDIDATES", ())
    g = topology.service_graph()
    assert g == {"nodes": [], "edges": [], "source": None}


def test_table_docs_only_list_columns_pod_2_actually_writes():
    """Contract §2: every other bronze column stays at its ClickHouse default by design.
    Listing the full DDL would misrepresent what a consumer may rely on."""
    cols = {c[0] for c in topology.TABLE_DOCS["otel_logs"]["columns"]}
    assert "Body" in cols and "ServiceName" in cols
    assert "TraceFlags" not in cols and "ScopeName" not in cols


def test_optional_ids_are_documented_as_empty_string_never_null():
    doc = {c[0]: c[2] for c in topology.TABLE_DOCS["otel_logs"]["columns"]}
    assert "never NULL" in doc["TraceId"]


def test_the_empty_tables_carry_a_reason_not_just_a_name():
    for name, why in topology.EMPTY_BY_CONTRACT.items():
        assert name.startswith("otel_metrics_")
        assert "v1.0.0" in why


def test_the_validation_policy_is_the_MODE_not_the_config_key():
    """The regression this exists for: `CONTRACT["validation"]` was hard-coded to the
    literal string `"grpc_validation"` — the config KEY — and every board rendered it where
    it meant the mode. A policy board whose headline is the policy cannot guess it."""
    from flow_ui import topology

    assert topology.grpc_validation() in ("off", "warn", "strict", "unknown")
    assert topology.CONTRACT["validation"] == topology.grpc_validation()
    assert topology.CONTRACT["validation"] != "grpc_validation"


def test_an_unreadable_collector_config_reports_unknown_not_a_default(monkeypatch, tmp_path):
    """`warn` is the collector's default, which makes it exactly the wrong thing to assume:
    a board that shows `warn` when it cannot read the policy is indistinguishable from one
    reading a real `warn`, and the whole point of the panel is knowing which."""
    from flow_ui import topology

    monkeypatch.setattr(topology, "_COLLECTOR_CFG", (tmp_path / "nope.yaml",))
    assert topology.grpc_validation() == "unknown"
