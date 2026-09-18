"""
Aggregations over the llm_traces table.

Shared by GET /metrics/summary and scripts/metrics_report.py so the API and
the paper tables are computed by the same SQL. Every function takes an open
psycopg2 connection (RealDictCursor) and a lookback in hours; ``since`` may
be given instead as an ISO timestamp.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def _window(hours: float | None, since: str | None, until: str | None) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    end = datetime.fromisoformat(until) if until else now
    if since:
        start = datetime.fromisoformat(since)
    else:
        start = end - timedelta(hours=hours or 24)
    return start.isoformat(), end.isoformat()


def _rows(cur, sql: str, params: tuple) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def llm_by_stage(cur, start: str, end: str) -> list[dict[str, Any]]:
    return _rows(cur, """
        SELECT stage,
               COUNT(*)                                                   AS calls,
               ROUND(AVG(latency_ms))                                     AS latency_avg_ms,
               percentile_cont(0.5)  WITHIN GROUP (ORDER BY latency_ms)   AS latency_p50_ms,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)   AS latency_p95_ms,
               ROUND(AVG(prompt_tokens))                                  AS prompt_tokens_avg,
               ROUND(AVG(completion_tokens))                              AS completion_tokens_avg,
               SUM(prompt_tokens)                                         AS prompt_tokens_sum,
               SUM(completion_tokens)                                     AS completion_tokens_sum,
               SUM(cost_token_priced)                                     AS cost_token_priced_usd,
               SUM(cost_compute)                                          AS cost_compute_usd,
               SUM(CASE WHEN ok IS FALSE THEN 1 ELSE 0 END)               AS errors,
               SUM(CASE WHEN attrs ? 'requested_tools' THEN 1 ELSE 0 END) AS calls_requesting_tools
        FROM llm_traces
        WHERE kind = 'llm_call' AND ts >= %s AND ts < %s
        GROUP BY stage ORDER BY stage
    """, (start, end))


def stage_parse(cur, start: str, end: str) -> list[dict[str, Any]]:
    return _rows(cur, """
        SELECT stage,
               COUNT(*)                                                          AS runs,
               percentile_cont(0.5)  WITHIN GROUP (ORDER BY latency_ms)          AS latency_p50_ms,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)          AS latency_p95_ms,
               SUM(CASE WHEN (attrs->>'parse_ok')::boolean THEN 1 ELSE 0 END)   AS parse_ok,
               SUM(CASE WHEN (attrs->>'empty_output')::boolean THEN 1 ELSE 0 END) AS empty_output,
               ROUND(AVG((attrs->>'output_chars')::numeric))                    AS output_chars_avg
        FROM llm_traces
        WHERE kind = 'stage' AND ts >= %s AND ts < %s
        GROUP BY stage ORDER BY stage
    """, (start, end))


def turns(cur, start: str, end: str) -> dict[str, Any]:
    summary = _rows(cur, """
        SELECT COUNT(*)                                                                 AS turns,
               percentile_cont(0.5)  WITHIN GROUP (ORDER BY latency_ms)                 AS e2e_p50_ms,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)                 AS e2e_p95_ms,
               ROUND(AVG(latency_ms))                                                   AS e2e_avg_ms,
               ROUND(AVG((attrs->>'stage_sum_vs_e2e')::numeric), 3)                    AS llm_share_of_e2e,
               ROUND(AVG((attrs->>'llm_calls')::numeric), 2)                           AS llm_calls_avg,
               ROUND(AVG(prompt_tokens))                                                AS prompt_tokens_avg,
               ROUND(AVG(completion_tokens))                                            AS completion_tokens_avg,
               AVG(cost_token_priced)                                                   AS cost_token_priced_avg_usd,
               SUM(cost_token_priced)                                                   AS cost_token_priced_sum_usd,
               AVG(cost_compute)                                                        AS cost_compute_avg_usd,
               SUM(CASE WHEN NOT (attrs->>'intent_parse_ok')::boolean THEN 1 ELSE 0 END) AS intent_unknown,
               SUM(CASE WHEN NOT (attrs->>'safety_parse_ok')::boolean THEN 1 ELSE 0 END) AS safety_unparsed,
               SUM(CASE WHEN (attrs->>'emergency_triggered')::boolean THEN 1 ELSE 0 END) AS emergencies,
               SUM(CASE WHEN (attrs->>'empty_final')::boolean THEN 1 ELSE 0 END)        AS empty_final,
               SUM((attrs->>'already_called')::int)                                     AS already_called_total,
               SUM((attrs->>'tool_errors')::int)                                        AS tool_errors_total
        FROM llm_traces
        WHERE kind = 'turn' AND ts >= %s AND ts < %s
    """, (start, end))
    intents = _rows(cur, """
        SELECT COALESCE(attrs->>'intent', 'unknown') AS intent,
               COALESCE(attrs->>'safety_status', 'UNPARSED') AS safety_status,
               COUNT(*) AS turns,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) AS e2e_p50_ms,
               AVG(cost_token_priced) AS cost_token_priced_avg_usd
        FROM llm_traces
        WHERE kind = 'turn' AND ts >= %s AND ts < %s
        GROUP BY 1, 2 ORDER BY turns DESC
    """, (start, end))
    return {"summary": summary[0] if summary else {}, "by_intent": intents}


def tools(cur, start: str, end: str) -> list[dict[str, Any]]:
    return _rows(cur, """
        SELECT name AS tool,
               COUNT(*)                                                           AS calls,
               percentile_cont(0.5)  WITHIN GROUP (ORDER BY latency_ms)           AS latency_p50_ms,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)           AS latency_p95_ms,
               MAX(latency_ms)                                                    AS latency_max_ms,
               SUM(CASE WHEN (attrs->>'already_called')::boolean THEN 1 ELSE 0 END) AS already_called,
               SUM(CASE WHEN ok IS FALSE THEN 1 ELSE 0 END)                       AS errors
        FROM llm_traces
        WHERE kind = 'tool_call' AND ts >= %s AND ts < %s
        GROUP BY name ORDER BY calls DESC
    """, (start, end))


def serpapi(cur, start: str, end: str) -> list[dict[str, Any]]:
    return _rows(cur, """
        SELECT name AS engine, COUNT(*) AS calls,
               SUM((attrs->>'cost')::numeric) AS cost_usd,
               SUM(CASE WHEN ok IS FALSE THEN 1 ELSE 0 END) AS failures
        FROM llm_traces
        WHERE kind = 'serpapi_call' AND ts >= %s AND ts < %s
        GROUP BY name ORDER BY calls DESC
    """, (start, end))


def emergency(cur, start: str, end: str) -> dict[str, Any]:
    rows = _rows(cur, """
        SELECT kind, COUNT(*) AS n,
               SUM(CASE WHEN ok THEN 1 ELSE 0 END) AS ok,
               SUM((attrs->>'sent')::int) AS sent,
               SUM((attrs->>'failed')::int) AS failed
        FROM llm_traces
        WHERE kind IN ('emergency_report', 'emergency_notify') AND ts >= %s AND ts < %s
        GROUP BY kind
    """, (start, end))
    return {r["kind"]: r for r in rows}


def http(cur, start: str, end: str) -> list[dict[str, Any]]:
    return _rows(cur, """
        SELECT attrs->>'method' AS method, name AS path, COUNT(*) AS requests,
               percentile_cont(0.5)  WITHIN GROUP (ORDER BY latency_ms) AS latency_p50_ms,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS latency_p95_ms,
               SUM(CASE WHEN ok IS FALSE THEN 1 ELSE 0 END) AS errors_5xx
        FROM llm_traces
        WHERE kind = 'http_request' AND ts >= %s AND ts < %s
        GROUP BY 1, 2 ORDER BY requests DESC LIMIT 30
    """, (start, end))


def summary(conn, hours: float | None = 24, since: str | None = None, until: str | None = None) -> dict[str, Any]:
    """Everything, as one JSON-serialisable dict."""
    start, end = _window(hours, since, until)
    cur = conn.cursor()
    try:
        return {
            "window": {"start": start, "end": end},
            "llm_by_stage": llm_by_stage(cur, start, end),
            "stages": stage_parse(cur, start, end),
            "turns": turns(cur, start, end),
            "tools": tools(cur, start, end),
            "serpapi": serpapi(cur, start, end),
            "emergency": emergency(cur, start, end),
            "http": http(cur, start, end),
        }
    finally:
        cur.close()
