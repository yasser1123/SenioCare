"""Push-notification text must not carry health details (it can show on a locked screen)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("app_notifications", ROOT / "app" / "notifications.py")
notifications = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notifications)

SUMMARY = "السكر 40 وعرقان جدا - Warfarin 5mg"


def test_notification_body_never_includes_the_report_summary():
    for kind in ("emergency", "daily", "weekly", "monthly", "other"):
        title, body, priority = notifications._build_notification_content("Ahmed", kind, SUMMARY)
        assert SUMMARY not in body and "40" not in body and "Warfarin" not in body
        assert "Ahmed" in title
        assert priority == ("urgent" if kind == "emergency" else "normal")
