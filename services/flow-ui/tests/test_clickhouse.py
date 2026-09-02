"""Silver's state is read from `system.tables`, so the parsing is the whole risk."""

import asyncio

import httpx
import pytest

from flow_ui.clickhouse import ClickHouse


def silver(rows: str | Exception) -> dict:
    ch = ClickHouse("http://ch:8123", "bronze")

    async def _query(_sql: str) -> str:
        if isinstance(rows, Exception):
            raise rows
        return rows

    ch._query = _query  # type: ignore[method-assign]
    return asyncio.run(ch.silver_state())


def test_engine_decides_what_a_table_counts_as():
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


def test_an_empty_silver_is_present_and_an_absent_one_is_not():
    """A volume older than the Silver DDL has no `silver` database at all.

    Both states are normal — the MVs do not POPULATE, so a fresh stack has the tables
    and no rows — but the board says different things about them, so they must not
    collapse into the same snapshot.
    """
    empty = silver("MergeTree\toperation_executions\t0\n")
    assert empty["present"] is True and empty["models"] == {"operation_executions": 0}

    absent = silver("")
    assert absent["present"] is False and absent["models"] == {}


def test_an_unreachable_clickhouse_reads_as_absent_rather_than_raising():
    """The slow lane must not take the board down because Silver could not be probed."""
    assert silver(httpx.ConnectError("refused")) == {
        "present": False, "models": {}, "views": [], "mvs": 0}


@pytest.mark.parametrize("line", ["", "   ", "MergeTree\tno_count_column"])
def test_a_row_that_does_not_parse_is_skipped_not_fatal(line):
    assert silver(f"MergeTree\tlog_events\t3\n{line}\n")["models"] == {"log_events": 3}


def schema(keys: str, cols: str) -> dict:
    ch = ClickHouse("http://ch:8123", "bronze")
    seen: list[str] = []

    async def _query(sql: str) -> str:
        seen.append(sql)
        if isinstance(keys, Exception):
            raise keys
        return keys if "system.tables" in sql else cols

    ch._query = _query  # type: ignore[method-assign]
    return asyncio.run(ch.silver_schema())


def test_only_the_physical_models_get_a_schema():
    """`system.columns` also returns the MVs and read views.

    An MV's columns are its target's, so an unfiltered read returned each model's schema
    three times under three names. Filtering happens in Python because ClickHouse 24.3
    rejects `IN (SELECT … FROM system.tables)` with "Not-ready Set".
    """
    state = schema(
        "log_events\tscenario, event_time\ttoDate(event_time)\n",
        "log_events\tevent_time\tDateTime64(9)\n"
        "log_events\tbody\tString\n"
        "log_events_mv\tevent_time\tDateTime64(9)\n"
        "log_health_1m\twindow_start\tDateTime\n",
    )
    assert list(state) == ["log_events"]
    assert state["log_events"]["columns"] == [
        ["event_time", "DateTime64(9)"], ["body", "String"]]
    assert state["log_events"]["order_by"] == "scenario, event_time"


def test_a_model_carries_its_hand_written_purpose():
    """Columns are metadata and cannot drift. A purpose is a claim, so it is written down."""
    state = schema("log_events\tk\tp\n", "log_events\tbody\tString\n")
    assert "one row per log record" in state["log_events"]["summary"].lower()


def test_an_unreachable_clickhouse_yields_no_schema_rather_than_raising():
    assert schema(httpx.ConnectError("refused"), "") == {}


def test_every_read_view_the_box_lists_has_something_to_say_about_itself():
    """Six names with no explanation is a list, not information."""
    for name, (grain, what) in ClickHouse.SILVER_VIEW_DOCS.items():
        assert grain and what, name
        assert len(what) <= 41, (name, len(what))
