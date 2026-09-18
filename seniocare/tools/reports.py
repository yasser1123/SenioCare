"""
Report Generation Service
=========================

Aggregates health data from multiple sources, feeds it to the Report Agent,
and stores the generated report in the database.

The Report Agent now outputs markdown text (not JSON), matching the chat
response style. Flutter can render it directly.

Data sources:
  - ADK session history (conversation intents, topics discussed)
  - medical_reports table (analyzed medical report images)
  - User profile state (medications, conditions, allergies)
  - emergency_events table (emergency triggers)

Trigger sources:
  - API endpoint (manual request from Flutter — elder or caregiver)
  - Backend cron job (scheduled periodic generation)
  - Emergency system (auto-generated on SOS trigger)
"""

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from seniocare import observability as obs
from seniocare.data.database import get_connection
from seniocare.observability import parse_intent, parse_safety_status


# ---------------------------------------------------------------------------
# Health Reports Table Management
# ---------------------------------------------------------------------------

def ensure_health_reports_table() -> None:
    """Create the health_reports table if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS health_reports (
                report_id        TEXT PRIMARY KEY,
                user_id          TEXT NOT NULL,
                report_type      TEXT NOT NULL,
                period_start     TEXT,
                period_end       TEXT,
                title            TEXT NOT NULL,
                content          TEXT NOT NULL,
                overall_status   TEXT,
                key_highlights   TEXT,
                recommendations  TEXT,
                doctor_notes     TEXT,
                generated_at     TEXT NOT NULL,
                source_data      TEXT
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_health_reports_user "
            "ON health_reports(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_health_reports_type "
            "ON health_reports(user_id, report_type)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_health_reports_date "
            "ON health_reports(user_id, generated_at)"
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Date Range Helpers
# ---------------------------------------------------------------------------

def _get_period_for_type(report_type: str) -> tuple[str, str]:
    """Calculate the date range for a report type.

    Args:
        report_type: 'daily', 'weekly', 'monthly', or 'emergency'

    Returns:
        Tuple of (start_date, end_date) in ISO format.
    """
    now = datetime.now()
    end_date = now.strftime("%Y-%m-%d")

    if report_type == "daily":
        start_date = end_date  # Same day
    elif report_type == "weekly":
        start = now - timedelta(days=7)
        start_date = start.strftime("%Y-%m-%d")
    elif report_type == "monthly":
        start = now - timedelta(days=30)
        start_date = start.strftime("%Y-%m-%d")
    elif report_type == "emergency":
        # Last 3 days of context for emergency
        start = now - timedelta(days=3)
        start_date = start.strftime("%Y-%m-%d")
    else:
        start_date = end_date

    return start_date, end_date


# ---------------------------------------------------------------------------
# Data Aggregation
# ---------------------------------------------------------------------------

def _get_medical_reports(user_id: str, start_date: str, end_date: str) -> list[dict]:
    """Get analyzed medical reports within a date range."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT report_type, report_date, key_findings, lab_values,
                   health_summary, severity_level, recommendations, scanned_at
            FROM medical_reports
            WHERE user_id = %s AND scanned_at >= %s AND scanned_at <= %s
            ORDER BY scanned_at DESC
            """,
            (user_id, start_date, end_date + "T23:59:59"),
        )
        rows = cursor.fetchall()
        conn.close()

        reports = []
        for row in rows:
            row = dict(row)
            row["key_findings"] = json.loads(row.get("key_findings", "[]"))
            row["lab_values"] = json.loads(row.get("lab_values", "{}"))
            row["recommendations"] = json.loads(row.get("recommendations", "[]"))
            reports.append(row)

        return reports
    except Exception:
        return []


async def _get_user_profile_from_session(user_id: str) -> dict:
    """Fetch the elder's profile from ADK session state.

    Reads user:-prefixed keys that were stored via /set-user-profile.
    Returns a dict ready for the Report Agent.
    """
    try:
        from app.config import session_service
        import uuid as _uuid

        temp_session_id = f"_report_profile_{_uuid.uuid4().hex[:8]}"
        session = await session_service.create_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=temp_session_id,
        )

        profile = {
            "name": session.state.get("user:user_name", "المستخدم"),
            "age": session.state.get("user:age", "غير محدد"),
            "conditions": session.state.get("user:chronicDiseases", []),
            "medications": session.state.get("user:medications", []),
            "allergies": session.state.get("user:allergies", []),
            "mobility": session.state.get("user:mobilityStatus", "غير محدد"),
            "weight": session.state.get("user:weight"),
            "height": session.state.get("user:height"),
            "gender": session.state.get("user:gender"),
            "bloodType": session.state.get("user:bloodType"),
        }

        await session_service.delete_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=temp_session_id,
        )

        return profile

    except Exception as e:
        print(f"[Report] Could not fetch user profile for {user_id}: {e}")
        return {
            "name": "المستخدم",
            "age": "غير محدد",
            "conditions": [],
            "medications": [],
            "allergies": [],
            "mobility": "غير محدد",
        }


def _empty_session_data() -> dict:
    return {
        "conversation_topics": [],
        "symptoms_reported": [],
        "meals_accessed": [],
        "exercises_accessed": [],
        "interaction_warnings": [],
        "emergency_events": [],
        "sessions_in_period": 0,
        "turns_in_period": 0,
    }


def _date_bounds(start_date: Optional[str], end_date: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    """ISO dates -> epoch seconds [start, end of end-day]. None when unset/unparseable."""
    def parse(d: Optional[str], end: bool) -> Optional[float]:
        if not d:
            return None
        try:
            dt = datetime.fromisoformat(str(d))
        except ValueError:
            return None
        if end and len(str(d)) <= 10:
            dt = dt + timedelta(days=1) - timedelta(microseconds=1)
        if dt.tzinfo is None:
            dt = dt.astimezone()  # local time, like datetime.now() used by the schedulers
        return dt.timestamp()
    return parse(start_date, False), parse(end_date, True)


def _event_ts(event: Any) -> Optional[float]:
    ts = getattr(event, "timestamp", None)
    return float(ts) if isinstance(ts, (int, float)) else None


def extract_session_facts(events: list, start_ts: Optional[float] = None, end_ts: Optional[float] = None,
                          session_id: str = "") -> dict:
    """Pure: walk one session's events inside [start_ts, end_ts] and collect what the
    pipeline actually did — from the tool calls and responses it recorded, not from
    guesses. This is what populates symptoms_reported, meals_accessed,
    exercises_accessed and interaction_warnings (AUDIT C-08: they were declared,
    read by the prompt, and never written)."""
    facts = _empty_session_data()
    turns = 0
    for event in events or []:
        ts = _event_ts(event)
        if ts is not None and ((start_ts is not None and ts < start_ts) or (end_ts is not None and ts > end_ts)):
            continue
        author = getattr(event, "author", None)
        content = getattr(event, "content", None)
        parts = list(getattr(content, "parts", None) or []) if content else []
        for part in parts:
            text = getattr(part, "text", None)
            if text and author == "user" and text.strip():
                turns += 1
                facts["conversation_topics"].append(text.strip()[:100])
            if text and author == "orchestrator_agent":
                intent = parse_intent(text)
                status = parse_safety_status(text)
                if intent and intent not in facts["conversation_topics"]:
                    facts["conversation_topics"].append(intent)
                if status == "EMERGENCY" or intent == "emergency":
                    facts["emergency_events"].append({
                        "session_id": session_id, "timestamp": _iso(ts), "trigger": "chat_emergency_detected",
                    })
            fc = getattr(part, "function_call", None)
            if fc is not None and getattr(fc, "name", None) == "assess_symptoms":
                args = dict(getattr(fc, "args", None) or {})
                for sym in args.get("symptoms") or []:
                    facts["symptoms_reported"].append({"symptom": str(sym), "timestamp": _iso(ts)})
            fr = getattr(part, "function_response", None)
            if fr is None or not getattr(fr, "name", None):
                continue
            resp = getattr(fr, "response", None) or {}
            if not isinstance(resp, dict):
                continue
            name = fr.name
            if name == "assess_symptoms" and resp.get("status") == "success":
                top = (resp.get("matches") or [{}])[0]
                facts["symptoms_reported"].append({
                    "assessment": resp.get("overall_severity"), "top_match": top.get("disease_name"),
                    "confidence": top.get("confidence"), "is_emergency": resp.get("is_emergency"), "timestamp": _iso(ts),
                })
            elif name == "get_meal_options" and resp.get("status") == "success":
                for m in resp.get("options") or []:
                    facts["meals_accessed"].append({"meal": m.get("name_ar") or m.get("name_en"), "timestamp": _iso(ts)})
            elif name == "get_meal_recipe" and resp.get("status") == "success":
                meal = resp.get("meal") or resp
                facts["meals_accessed"].append({"meal": meal.get("name_ar") or meal.get("meal_id"), "recipe": True, "timestamp": _iso(ts)})
            elif name == "get_exercises" and resp.get("status") == "success":
                for ex in resp.get("exercises") or []:
                    facts["exercises_accessed"].append({"exercise": ex.get("name_ar") or ex.get("name_en"), "timestamp": _iso(ts)})
            elif name == "check_drug_food_interaction" and resp.get("status") == "success":
                for h in resp.get("harmful_interactions") or []:
                    facts["interaction_warnings"].append({
                        "drug": h.get("drug"), "food": h.get("food"), "severity": h.get("severity"), "timestamp": _iso(ts),
                    })
    facts["turns_in_period"] = turns
    facts["sessions_in_period"] = 1 if turns else 0
    return facts


def _iso(ts: Optional[float]) -> Optional[str]:
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds") if ts else None


def _merge_facts(into: dict, facts: dict) -> None:
    for key, value in facts.items():
        if isinstance(value, list):
            into[key].extend(value)
        elif isinstance(value, (int, float)):
            into[key] = into.get(key, 0) + value


async def _get_session_data_from_history(
    user_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None,
) -> dict:
    """Conversation facts for `user_id` inside the report period (AUDIT C-07:
    the period used to be ignored, so a daily and a monthly report saw the
    same data)."""
    session_data = _empty_session_data()
    start_ts, end_ts = _date_bounds(start_date, end_date)
    try:
        from app.config import APP_NAME, session_service

        listing = await session_service.list_sessions(app_name=APP_NAME, user_id=user_id)
        if not listing or not listing.sessions:
            return session_data
        for info in listing.sessions:
            if str(info.id).startswith("_"):
                continue  # temp sessions
            last = getattr(info, "last_update_time", None)
            if start_ts is not None and isinstance(last, (int, float)) and last < start_ts:
                continue  # untouched since before the period
            try:
                session = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=info.id)
            except Exception:  # noqa: BLE001
                continue
            if not session:
                continue
            _merge_facts(session_data, extract_session_facts(getattr(session, "events", []), start_ts, end_ts, info.id))
    except Exception as e:  # noqa: BLE001
        print(f"[Report] Could not extract session data for {user_id}: {e}")
    # de-duplicate topic strings, keep order
    session_data["conversation_topics"] = list(dict.fromkeys(session_data["conversation_topics"]))
    return session_data


async def aggregate_report_data(
    user_id: str,
    report_type: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    emergency_context: Optional[dict] = None,
) -> dict:
    """Aggregate all health data for report generation.

    Automatically fetches user profile from session state and
    conversation data from session history.

    Args:
        user_id: The user's identifier.
        report_type: Type of report ('daily', 'weekly', 'monthly', 'emergency').
        start_date: Override start date (ISO format).
        end_date: Override end date (ISO format).
        emergency_context: Pre-built emergency data (from callback, when available).

    Returns:
        dict: Aggregated data package ready for the Report Agent.
    """
    # Determine period
    if not start_date or not end_date:
        start_date, end_date = _get_period_for_type(report_type)

    # Auto-fetch user profile from session state
    user_profile = await _get_user_profile_from_session(user_id)

    # Auto-fetch session data from history, restricted to the period (C-07)
    session_data = await _get_session_data_from_history(user_id, start_date, end_date)

    # Merge emergency context if provided (from callback)
    if emergency_context:
        session_data["emergency_events"] = emergency_context.get(
            "emergency_events", session_data.get("emergency_events", [])
        )
        # Add any extra conversation topics from the emergency
        extra_topics = emergency_context.get("conversation_topics", [])
        session_data["conversation_topics"].extend(extra_topics)

    # Get medical reports from DB
    medical_reports = _get_medical_reports(user_id, start_date, end_date)

    # Build aggregated data package
    aggregated = {
        "report_type": report_type,
        "period": {"start": start_date, "end": end_date},
        "user_profile": user_profile,
        "conversation_topics": session_data.get("conversation_topics", []),
        "symptoms_reported": session_data.get("symptoms_reported", []),
        "meals_accessed": session_data.get("meals_accessed", []),
        "exercises_accessed": session_data.get("exercises_accessed", []),
        "medical_reports_analyzed": medical_reports,
        "interaction_warnings": session_data.get("interaction_warnings", []),
        "emergency_events": session_data.get("emergency_events", []),
    }
    # Tell the Report Agent what is genuinely absent, so it says "no data"
    # instead of inventing trends from empty arrays (AUDIT C-08).
    empty = [k for k in ("symptoms_reported", "meals_accessed", "exercises_accessed",
                         "interaction_warnings", "emergency_events", "medical_reports_analyzed")
             if not aggregated.get(k)]
    aggregated["data_coverage"] = {
        "sessions_in_period": session_data.get("sessions_in_period", 0),
        "turns_in_period": session_data.get("turns_in_period", 0),
        "fields_with_no_data": empty,
        "note": "Fields listed in fields_with_no_data had NO records in this period. State that plainly; do not infer trends from them.",
    }

    return aggregated


# ---------------------------------------------------------------------------
# Report Generation (via Report Agent)
# ---------------------------------------------------------------------------

async def generate_report(
    user_id: str,
    report_type: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    emergency_context: Optional[dict] = None,
) -> dict:
    """Generate a health report using the Report Agent.

    All data is automatically fetched from session state and database.
    Only user_id and report_type are required.

    This function:
      1. Fetches user profile from ADK session state
      2. Extracts conversation data from session history
      3. Aggregates medical reports from database
      4. Sends everything to the Report Agent
      5. Parses the markdown output
      6. Stores the report in the health_reports table
      7. Returns the report

    Args:
        user_id: The user's identifier.
        report_type: 'daily', 'weekly', 'monthly', or 'emergency'.
        start_date: Override start date.
        end_date: Override end date.
        emergency_context: Emergency data from chat callback (optional).

    Returns:
        dict: The generated report with report_id.
    """
    # Ensure table exists
    ensure_health_reports_table()

    # Aggregate data (auto-fetches profile + session history)
    aggregated = await aggregate_report_data(
        user_id=user_id,
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        emergency_context=emergency_context,
    )

    # Call the Report Agent via the ADK Runner
    raw_response = await _call_report_agent(aggregated)

    # Parse the markdown response — extract status and content
    overall_status, content, title = _parse_markdown_report(
        raw_response, report_type, aggregated.get("user_profile")
    )

    # Generate report ID and store
    report_id = f"HR_{uuid.uuid4().hex[:12]}"
    now = datetime.now().isoformat()

    stored = _store_health_report(
        report_id=report_id,
        user_id=user_id,
        report_type=report_type,
        period_start=aggregated["period"]["start"],
        period_end=aggregated["period"]["end"],
        content=content,
        title=title,
        overall_status=overall_status,
        generated_at=now,
        source_data=aggregated,
    )

    return {
        "report_id": report_id,
        "user_id": user_id,
        "report_type": report_type,
        "period": aggregated["period"],
        "title": title,
        "overall_status": overall_status,
        "content": content,
        "generated_at": now,
        "stored_in_db": stored,
    }


async def _call_report_agent(aggregated_data: dict) -> str:
    """Call the Report Agent with aggregated data.

    Uses the ADK Runner to send a message to the report_agent
    and collect its markdown response.

    Returns:
        Raw markdown text from the agent.
    """
    from seniocare.sub_agents.report_agent import report_agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    import uuid as _uuid

    # Create a temporary session for the report agent
    session_service = InMemorySessionService()
    runner = Runner(
        agent=report_agent,
        app_name="seniocare_reports",
        session_service=session_service,
    )

    session = await session_service.create_session(
        app_name="seniocare_reports",
        user_id="system",
        session_id=f"report_{_uuid.uuid4().hex[:8]}",
    )

    # Send the aggregated data as a message
    prompt = (
        "Generate a health report from the following aggregated data. "
        "Return the report as formatted markdown in Egyptian Arabic "
        "as specified in your instructions.\n\n"
        f"{json.dumps(aggregated_data, ensure_ascii=False, indent=2)}"
    )

    message = types.Content(
        role="user",
        parts=[types.Part(text=prompt)],
    )

    # Run the agent and keep the FINAL response only. Concatenating every
    # event's text (the previous behaviour, AUDIT R-05) could stitch partial
    # or intermediate outputs into the stored report.
    final_text = ""
    all_text = ""
    async for event in runner.run_async(
        user_id="system",
        session_id=session.id,
        new_message=message,
    ):
        if not (event.content and event.content.parts):
            continue
        chunk = "".join(part.text for part in event.content.parts if getattr(part, "text", None))
        if not chunk:
            continue
        all_text += chunk
        try:
            is_final = event.is_final_response()
        except Exception:  # noqa: BLE001
            is_final = False
        if is_final and getattr(event, "author", None) == report_agent.name:
            final_text = chunk

    return (final_text or all_text).strip()


def _parse_markdown_report(
    raw_text: str,
    report_type: str,
    user_profile: Optional[dict] = None,
) -> tuple[str, str, str]:
    """Parse the Report Agent's markdown response.

    Extracts:
      - overall_status from the STATUS: line
      - content (the full markdown without the STATUS line)
      - title (from the first heading line)

    Returns:
        Tuple of (overall_status, content, title).
    """
    raw_text = raw_text.strip()

    # Strip any code fences the model might add
    if raw_text.startswith("```"):
        parts = raw_text.split("```")
        if len(parts) >= 2:
            raw_text = parts[1]
            # Remove language tag like ```markdown
            if raw_text.startswith("markdown"):
                raw_text = raw_text[8:]
        raw_text = raw_text.strip()

    # Extract STATUS line. An absent or unrecognised value is "unknown" and is
    # recorded as a parse failure; it used to default to "moderate", which
    # caregivers would read as a real assessment (AUDIT C-10).
    overall_status = "unknown"
    status_match = re.search(r"^\**\s*STATUS\s*[:：]\s*\**\s*([A-Za-z]+)", raw_text, re.MULTILINE | re.IGNORECASE)
    if status_match:
        status_val = status_match.group(1).lower().strip()
        if status_val in ("good", "moderate", "concerning", "critical"):
            overall_status = status_val
        # Remove the STATUS line from content
        raw_text = raw_text[:status_match.start()] + raw_text[status_match.end():]
        raw_text = raw_text.strip()
    obs.emit("report_parse", report_type=report_type, ok=overall_status != "unknown",
             status=overall_status, chars=len(raw_text))

    # Extract title from first line containing report emoji
    title = _extract_title(raw_text, report_type, user_profile)

    # Content is the full markdown text
    content = raw_text if raw_text else _generate_fallback_report(
        report_type, user_profile
    )

    return overall_status, content, title


def _extract_title(
    text: str,
    report_type: str,
    user_profile: Optional[dict] = None,
) -> str:
    """Extract the report title from the first heading line."""
    user_name = (user_profile or {}).get("name", "المستخدم")
    type_labels = {
        "daily": "يومي",
        "weekly": "أسبوعي",
        "monthly": "شهري",
        "emergency": "طوارئ",
    }

    # Try to find a title line (starts with emoji or #)
    for line in text.split("\n")[:5]:
        line = line.strip()
        if line and (line.startswith("📋") or line.startswith("🚨")
                     or line.startswith("📊") or line.startswith("📈")
                     or line.startswith("#")):
            # Clean markdown heading markers
            title = line.lstrip("#").strip()
            if title:
                return title

    # Fallback title
    type_label = type_labels.get(report_type, "صحي")
    return f"تقرير {type_label} — {user_name}"


def _generate_fallback_report(
    report_type: str,
    user_profile: Optional[dict] = None,
) -> str:
    """Generate a minimal fallback report if agent returns empty."""
    user_name = (user_profile or {}).get("name", "المستخدم")
    type_labels = {
        "daily": "يومي",
        "weekly": "أسبوعي",
        "monthly": "شهري",
        "emergency": "طوارئ",
    }
    type_label = type_labels.get(report_type, "صحي")

    return (
        f"📋 تقرير {type_label} — {user_name}\n\n"
        f"يا فندم، للأسف مفيش بيانات كافية لإنشاء تقرير مفصل في الفترة دي. 💚\n\n"
        f"📌 التوصيات:\n"
        f"1. حافظ على متابعة صحتك مع النظام\n"
        f"2. سجل أي أعراض أو ملاحظات عشان التقرير الجاي يبقى أشمل\n\n"
        f"ربنا يديم عليك الصحة يا فندم 💚"
    )


# ---------------------------------------------------------------------------
# Database Storage
# ---------------------------------------------------------------------------

def _store_health_report(
    report_id: str,
    user_id: str,
    report_type: str,
    period_start: str,
    period_end: str,
    content: str,
    title: str,
    overall_status: str,
    generated_at: str,
    source_data: dict,
) -> bool:
    """Store a generated health report in the database."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO health_reports
            (report_id, user_id, report_type, period_start, period_end,
             title, content, overall_status, key_highlights,
             recommendations, doctor_notes, generated_at, source_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (report_id) DO NOTHING
            """,
            (
                report_id,
                user_id,
                report_type,
                period_start,
                period_end,
                title,
                content,
                overall_status,
                "[]",  # key_highlights not used in markdown format
                "[]",  # recommendations embedded in markdown
                "",    # doctor_notes embedded in markdown
                generated_at,
                json.dumps(source_data, ensure_ascii=False),
            ),
        )

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"[Report Storage] Error storing report: {e}")
        return False


# ---------------------------------------------------------------------------
# Report Retrieval
# ---------------------------------------------------------------------------

def get_health_reports(
    user_id: str,
    report_type: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """Retrieve health reports for a user.

    Args:
        user_id: The user's identifier.
        report_type: Optional filter by report type.
        limit: Max number of reports to return.

    Returns:
        List of report records.
    """
    ensure_health_reports_table()

    try:
        conn = get_connection()
        cursor = conn.cursor()

        if report_type:
            cursor.execute(
                """
                SELECT report_id, user_id, report_type, period_start, period_end,
                       title, overall_status, generated_at
                FROM health_reports
                WHERE user_id = %s AND report_type = %s
                ORDER BY generated_at DESC
                LIMIT %s
                """,
                (user_id, report_type, limit),
            )
        else:
            cursor.execute(
                """
                SELECT report_id, user_id, report_type, period_start, period_end,
                       title, overall_status, generated_at
                FROM health_reports
                WHERE user_id = %s
                ORDER BY generated_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    except Exception:
        return []


def get_health_report_detail(report_id: str) -> Optional[dict]:
    """Retrieve a single health report with full content.

    Args:
        report_id: The report's identifier.

    Returns:
        Full report record or None if not found.
    """
    ensure_health_reports_table()

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM health_reports WHERE report_id = %s",
            (report_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            row = dict(row)
            # Don't expose source_data in detail view (it can be large)
            row.pop("source_data", None)
            return row

        return None

    except Exception:
        return None
