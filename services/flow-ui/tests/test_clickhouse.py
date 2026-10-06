"""Silver's state is read from `system.tables`, so the parsing is the whole risk.

The `_query` fake and the coverage response builder come from `conftest.py`: the
dual-source boards assert both coverage branches, and a fake defined per file cannot be
shared with them.
"""

import asyncio

import httpx
import pytest

from flow_ui.clickhouse import ClickHouse


@pytest.fixture
def silver(run_query):
    def _silver(rows: str | Exception) -> dict:
        return run_query(rows, lambda ch: ch.silver_state())

    return _silver


def test_engine_decides_what_a_table_counts_as(silver):
    state = silver(
        "MergeTree\toperation_executions\t12849\n"
        "MergeTree\tlog_events\t7\n"
        "View\tservice_health_1m\t0\n"
        "View\tapi_latency_1m\t0\n"
        "MaterializedView\tmv_operation_executions\t0\n"
    )
    assert state["present"] is True
    assert state["models"] == {"operation_executions": 12849, "log_events": 7}
    assert state["views"] == ["api_latency_1m", "service_health_1m"]
    assert state["mvs"] == 1


def test_an_empty_silver_is_present_and_an_absent_one_is_not(silver):
    """A volume older than the Silver DDL has no `silver` database at all.

    Both states are normal — the MVs do not POPULATE, so a fresh stack has the tables
    and no rows — but the board says different things about them, so they must not
    collapse into the same snapshot.
    """
    empty = silver("MergeTree\toperation_executions\t0\n")
    assert empty["present"] is True and empty["models"] == {"operation_executions": 0}

    absent = silver("")
    assert absent["present"] is False and absent["models"] == {}


def test_an_unreachable_clickhouse_reads_as_absent_rather_than_raising(silver):
    """The slow lane must not take the board down because Silver could not be probed."""
    assert silver(httpx.ConnectError("refused")) == {
        "present": False, "models": {}, "views": [], "mvs": 0}


@pytest.mark.parametrize("line", ["", "   ", "MergeTree\tno_count_column"])
def test_a_row_that_does_not_parse_is_skipped_not_fatal(line, silver):
    assert silver(f"MergeTree\tlog_events\t3\n{line}\n")["models"] == {"log_events": 3}


@pytest.fixture
def sgraph(run_query):
    def _sgraph(rows, cols: str = "") -> dict:
        answers = rows if isinstance(rows, Exception) else {
            "system.tables": rows, "system.columns": cols}
        return run_query(answers, lambda ch: ch.silver_graph())

    return _sgraph


MV = ("CREATE MATERIALIZED VIEW silver.log_events_mv TO silver.log_events "
      "AS SELECT * FROM bronze.otel_logs")
VIEW = "CREATE VIEW silver.log_health_1m AS SELECT * FROM silver.log_events"
TBL = "CREATE TABLE silver.log_events (body String) ENGINE = MergeTree"


def test_the_three_kinds_are_told_apart_by_engine(sgraph):
    """A table stores rows, an MV is an insert trigger, a view is a query. Collapsing them
    is exactly the thing the board now exists to un-collapse."""
    g = sgraph(f"log_events\tMergeTree\tscenario\t{TBL}\n"
               f"log_events_mv\tMaterializedView\t\t{MV}\n"
               f"log_health_1m\tView\t\t{VIEW}\n")
    assert {k: v["kind"] for k, v in g.items()} == {
        "log_events": "table", "log_events_mv": "mv", "log_health_1m": "view"}


def test_an_mv_reads_its_from_and_writes_its_to(sgraph):
    """`TO silver.x` is the target and must not be reported as a source, or the MV would
    look like it reads the table it writes."""
    g = sgraph(f"log_events_mv\tMaterializedView\t\t{MV}\n")
    assert g["log_events_mv"]["sources"] == ["bronze.otel_logs"]
    assert g["log_events_mv"]["target"] == "log_events"


def test_a_view_reads_every_table_it_names(sgraph):
    ddl = ("CREATE VIEW silver.run_summary AS SELECT * FROM silver.log_events "
           "JOIN silver.operation_executions USING run_id")
    g = sgraph(f"run_summary\tView\t\t{ddl}\n")
    assert g["run_summary"]["sources"] == [
        "silver.log_events", "silver.operation_executions"]


def test_a_table_added_to_the_ddl_needs_no_code_change(sgraph):
    """The whole point of reading `system.tables`: the board is the database's shape, not a
    list maintained here. Verified live too — a view created in ClickHouse appeared on the
    board, wired to its source, with nothing edited."""
    g = sgraph("brand_new\tMergeTree\tid\tCREATE TABLE silver.brand_new (id UInt8) "
               "ENGINE = MergeTree\n")
    assert g["brand_new"]["kind"] == "table"


def test_an_mv_does_not_repeat_its_targets_columns(sgraph):
    """An MV's columns *are* its target's, so listing them says the same thing twice."""
    g = sgraph(f"log_events_mv\tMaterializedView\t\t{MV}\n",
               "log_events_mv\tbody\tString\n")
    assert g["log_events_mv"]["columns"] == []


def test_an_unreachable_clickhouse_yields_no_graph_rather_than_raising(sgraph):
    assert sgraph(httpx.ConnectError("refused")) == {}


def test_every_read_view_the_box_lists_has_something_to_say_about_itself():
    """Six names with no explanation is a list, not information."""
    for name, (grain, what) in ClickHouse.SILVER_VIEW_DOCS.items():
        assert grain and what, name
        assert len(what) <= 41, (name, len(what))


def test_the_whole_mergetree_family_is_a_table(sgraph):
    """A SummingMergeTree rollup is the obvious engine for a second-stage model.

    Matching the literal string "MergeTree" made one invisible on the board with its own MV
    left pointing at nothing — found by creating one against the live database, not in
    review. Anything that is not one of the two view engines stores rows.
    """
    ddl = "CREATE TABLE silver.log_events_hourly (n UInt64) ENGINE = SummingMergeTree"
    g = sgraph(f"log_events_hourly\tSummingMergeTree\tservice_name\t{ddl}\n")
    assert g["log_events_hourly"]["kind"] == "table"


def test_silver_state_classifies_engines_the_same_way(silver):
    """The two readings must agree, or the board draws a table it has no count for."""
    state = silver("SummingMergeTree\tlog_events_hourly\t22\n"
                   "MergeTree\tlog_events\t7\n"
                   "View\tlog_health_1m\t0\n"
                   "MaterializedView\tlog_events_hourly_mv\t0\n")
    assert state["models"] == {"log_events_hourly": 22, "log_events": 7}
    assert state["views"] == ["log_health_1m"] and state["mvs"] == 1


def test_a_second_stage_mv_reads_silver_not_bronze(sgraph):
    """An hourly rollup reads a silver table. Laid out by kind it fell back into the first
    column and its edge ran right to left; depth puts it after what it reads."""
    ddl = ("CREATE MATERIALIZED VIEW silver.log_events_hourly_mv TO silver.log_events_hourly "
           "AS SELECT count() FROM silver.log_events GROUP BY service_name")
    g = sgraph(f"log_events_hourly_mv\tMaterializedView\t\t{ddl}\n")
    assert g["log_events_hourly_mv"]["sources"] == ["silver.log_events"]
    assert g["log_events_hourly_mv"]["target"] == "log_events_hourly"


# ── the shared fixtures' own contract (REQ-E-13) ─────────────────────────────
#
# The dual-source boards read silver only when silver's history reaches back past the
# window they need. The decision is a comparison against `now`, so the builder that
# produces the probe response has to put the oldest silver row on the correct side of the
# window — and that is worth asserting here rather than discovering as a board that drew
# the wrong source.


def test_the_coverage_builder_offers_both_sides_of_the_window(silver_coverage):
    window = 60
    boundary = silver_coverage.now - window * 60

    covering = dict(_coverage_rows(silver_coverage.covering(window)))
    short = dict(_coverage_rows(silver_coverage.short_of(window)))

    assert set(covering) == set(short) == set(silver_coverage.tables)
    for table in silver_coverage.tables:
        assert covering[table] <= boundary, table
        assert short[table] > boundary, table


def test_an_absent_silver_is_a_third_state_not_a_zero(silver_coverage):
    """A volume older than the silver DDL has no rows to report a minimum over. It must
    not read as "oldest row at epoch 0", which covers every window there is."""
    assert silver_coverage.absent() == ""
    assert _coverage_rows(silver_coverage.absent()) == []


def test_the_query_stub_answers_per_statement_and_counts_what_it_was_asked(ch_stub):
    """REQ-E-14 is a statement about how many times a query is issued, so the fake has to
    record that, not just answer."""
    ch, stub = ch_stub({"system.tables": "a\tMergeTree\t1\n", "system.columns": "a\tb\tc\n"})
    assert "MergeTree" in asyncio.run(ch._query("... FROM system.tables ..."))
    assert stub.count_matching("system.tables") == 1
    assert stub.count_matching("system.columns") == 0


def _coverage_rows(tsv: str) -> list[tuple[str, int]]:
    return [(parts[0], int(parts[1]))
            for parts in (line.split("\t") for line in tsv.splitlines() if line.strip())]
