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
