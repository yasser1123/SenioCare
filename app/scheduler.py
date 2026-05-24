"""
Scheduled Report Generation
============================

Uses APScheduler to trigger periodic health report generation.
Reports are generated for all users who have had recent activity.
After generation, FCM push notifications are sent to linked caregivers.

Schedule:
  - Daily reports:   Every day at 23:00
  - Weekly reports:  Every Sunday at 23:00
  - Monthly reports: 1st of each month at 23:00

Usage:
  from app.scheduler import setup_scheduler
  setup_scheduler()  # Call once at app startup
"""

import asyncio
import logging
import uuid
from datetime import datetime

logger = logging.getLogger("seniocare.scheduler")


# ---------------------------------------------------------------------------
# Active user discovery
# ---------------------------------------------------------------------------

def _get_active_user_ids() -> list[str]:
    """Get user IDs that have had activity (for scheduled reports).

    Queries the medical_reports table for distinct users, and also
    checks health_reports for users who have received reports before.
    Only users with actual AI interaction data get scheduled reports.
    """
    from seniocare.data.database import get_connection

    user_ids = set()
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Users with medical reports
        cursor.execute("SELECT DISTINCT user_id FROM medical_reports")
        for row in cursor.fetchall():
            user_ids.add(row["user_id"])

        # Users who already have health reports
        try:
            cursor.execute("SELECT DISTINCT user_id FROM health_reports")
            for row in cursor.fetchall():
                user_ids.add(row["user_id"])
        except Exception:
            pass  # Table may not exist yet

        conn.close()
    except Exception as e:
        logger.warning(f"Could not query active users: {e}")

    return list(user_ids)


# ---------------------------------------------------------------------------
# Caregiver lookup from session state
# ---------------------------------------------------------------------------

async def _get_user_caregivers(user_id: str) -> tuple[str, list[dict]]:
    """Read caregivers and elder name from ADK session state.

    Args:
        user_id: The elder's user_id.

    Returns:
        Tuple of (elder_name, caregivers_list).
    """
    try:
        from app.config import session_service

        temp_session_id = f"_sched_read_{uuid.uuid4().hex[:8]}"
        session = await session_service.create_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=temp_session_id,
        )

        caregivers = session.state.get("user:caregivers", []) or []
        elder_name = session.state.get("user:user_name", "المستخدم")

        await session_service.delete_session(
            app_name="seniocare",
            user_id=user_id,
            session_id=temp_session_id,
        )

        return elder_name, caregivers

    except Exception as e:
        logger.warning(f"Could not read caregivers for {user_id}: {e}")
        return "المستخدم", []


# ---------------------------------------------------------------------------
# Scheduled job
# ---------------------------------------------------------------------------

async def _generate_scheduled_reports(report_type: str) -> None:
    """Generate reports for all active users and notify caregivers.

    Called by APScheduler on the configured schedule.
    """
    from seniocare.tools.reports import generate_report

    user_ids = _get_active_user_ids()
    if not user_ids:
        logger.info(f"[Scheduler] No active users for {report_type} reports")
        return

    logger.info(
        f"[Scheduler] Generating {report_type} reports for {len(user_ids)} users"
    )

    for user_id in user_ids:
        try:
            # Step 1: Generate the report
            result = await generate_report(
                user_id=user_id,
                report_type=report_type,
            )
            report_id = result.get("report_id", "unknown")
            logger.info(
                f"[Scheduler] {report_type} report generated for {user_id}: "
                f"{report_id}"
            )

            # Step 2: Notify caregivers via FCM
            try:
                elder_name, caregivers = await _get_user_caregivers(user_id)

                if caregivers:
                    from app.notifications import notify_caregivers

                    notif_result = await notify_caregivers(
                        caregivers=caregivers,
                        elder_name=elder_name,
                        report_type=report_type,
                        report_id=report_id,
                        elder_user_id=user_id,
                    )
                    logger.info(
                        f"[Scheduler] Notifications for {user_id}: "
                        f"{notif_result.get('sent', 0)} sent, "
                        f"{notif_result.get('failed', 0)} failed"
                    )
                else:
                    logger.info(
                        f"[Scheduler] No caregivers for {user_id} — skipping notification"
                    )

            except Exception as ne:
                logger.warning(
                    f"[Scheduler] Notification failed for {user_id}: {ne}"
                )

        except Exception as e:
            logger.error(
                f"[Scheduler] Failed to generate {report_type} report "
                f"for {user_id}: {e}"
            )


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

_scheduler = None


def setup_scheduler() -> None:
    """Configure and start the report generation scheduler.

    Call this once at application startup (e.g., in main.py).
    Idempotent — safe to call multiple times.
    """
    global _scheduler
    if _scheduler is not None:
        return  # Already running

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning(
            "[Scheduler] APScheduler not installed. "
            "Run: pip install apscheduler\n"
            "Scheduled reports will not run."
        )
        return

    _scheduler = AsyncIOScheduler()

    # Daily report at 23:00
    _scheduler.add_job(
        _generate_scheduled_reports,
        CronTrigger(hour=23, minute=0),
        args=["daily"],
        id="daily_reports",
        replace_existing=True,
    )

    # Weekly report every Sunday at 23:00
    _scheduler.add_job(
        _generate_scheduled_reports,
        CronTrigger(day_of_week="sun", hour=23, minute=0),
        args=["weekly"],
        id="weekly_reports",
        replace_existing=True,
    )

    # Monthly report on 1st of each month at 23:00
    _scheduler.add_job(
        _generate_scheduled_reports,
        CronTrigger(day=1, hour=23, minute=0),
        args=["monthly"],
        id="monthly_reports",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("[Scheduler] Report scheduler started")
    print("[Scheduler] ✅ Report scheduler started (daily/weekly/monthly)")


def shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("[Scheduler] Scheduler shut down")
