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
from datetime import datetime, timedelta
from typing import Optional

from seniocare.data.database import get_connection


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


async def _get_session_data_from_history(user_id: str) -> dict:
    """Extract conversation data from the user's session history.

    Reads recent session events to find conversation topics,
    symptoms reported, meals/exercises discussed, etc.
    """
    session_data = {
        "conversation_topics": [],
        "symptoms_reported": [],
        "meals_accessed": [],
        "exercises_accessed": [],
        "interaction_warnings": [],
        "emergency_events": [],
    }

    try:
        from app.config import session_service

        # List all sessions for this user
        sessions = await session_service.list_sessions(
            app_name="seniocare",
            user_id=user_id,
        )

        if not sessions or not sessions.sessions:
            return session_data

        # Collect orchestrator results from recent sessions
        for session_info in sessions.sessions[-10:]:  # last 10 sessions
            try:
                session = await session_service.get_session(
                    app_name="seniocare",
                    user_id=user_id,
                    session_id=session_info.id,
                )
                if not session:
                    continue

                # Extract orchestrator intent from session state
                orch_result = session.state.get("orchestrator_result", "")
                if orch_result:
                    import re
                    intent_match = re.search(r"INTENT:\s*(\w+)", orch_result)
                    if intent_match:
                        intent = intent_match.group(1).lower()
                        if intent not in session_data["conversation_topics"]:
                            session_data["conversation_topics"].append(intent)

                        if intent == "emergency":
                            session_data["emergency_events"].append({
                                "session_id": session_info.id,
                                "timestamp": getattr(session_info, "last_update_time", ""),
                            })

                # Extract conversation snippets from events
                if hasattr(session, "events"):
                    for event in session.events[-6:]:
                        if not hasattr(event, "content") or not event.content:
                            continue
                        if not event.content.parts:
                            continue
                        text = event.content.parts[0].text or ""
                        if event.author == "user" and text.strip():
                            session_data["conversation_topics"].append(
                                text[:100]
                            )

            except Exception:
                continue

    except Exception as e:
        print(f"[Report] Could not extract session data for {user_id}: {e}")

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

    # Auto-fetch session data from history
    session_data = await _get_session_data_from_history(user_id)

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

    # Run the agent and collect the response
    response_text = ""
    async for event in runner.run_async(
        user_id="system",
        session_id=session.id,
        new_message=message,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    response_text += part.text

    return response_text.strip()


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

    # Extract STATUS line
    overall_status = "moderate"
    status_match = re.search(r"^STATUS:\s*(\w+)", raw_text, re.MULTILINE)
    if status_match:
        status_val = status_match.group(1).lower().strip()
        if status_val in ("good", "moderate", "concerning", "critical"):
            overall_status = status_val
        # Remove the STATUS line from content
        raw_text = raw_text[:status_match.start()] + raw_text[status_match.end():]
        raw_text = raw_text.strip()

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
