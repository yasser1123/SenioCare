"""Metrics router: aggregated latency, tokens, cost and routing from llm_traces."""

import asyncio

from fastapi import APIRouter, HTTPException, Query

from app import metrics_queries
from seniocare import observability as obs

router = APIRouter(prefix="/metrics", tags=["Metrics"])


def _summary_sync(hours: float | None, since: str | None, until: str | None) -> dict:
    from seniocare.data.database import get_connection

    conn = get_connection()
    try:
        return metrics_queries.summary(conn, hours=hours, since=since, until=until)
    finally:
        conn.close()


@router.get("/summary")
async def metrics_summary(
    hours: float = Query(24, gt=0, le=24 * 90, description="Lookback window in hours (ignored when since is given)"),
    since: str | None = Query(None, description="ISO-8601 start, e.g. 2026-09-18T00:00:00+00:00"),
    until: str | None = Query(None, description="ISO-8601 end (default now)"),
):
    """p50/p95 latency per stage, tokens, three cost views, intent and safety
    distribution, tool latency and `already_called` rate, SerpAPI spend,
    emergency escalation success. Same SQL as scripts/metrics_report.py."""
    try:
        data = await asyncio.to_thread(_summary_sync, hours, since, until)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"metrics unavailable: {type(e).__name__}: {e}"[:300])
    data["sink"] = obs.sink_stats()
    return data
