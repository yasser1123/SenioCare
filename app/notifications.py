"""
FCM Notification Service
=========================

Sends push notifications to caregiver devices via Firebase Cloud Messaging.
Used after report generation (scheduled, emergency, or manual) to alert
linked caregivers about the elder's health status.

Setup:
  1. Place Firebase service account JSON in the project root.
  2. Set FIREBASE_CREDENTIALS_PATH in .env
  3. Call init_firebase() once at app startup.
"""

import logging
from typing import Optional

logger = logging.getLogger("seniocare.notifications")

_firebase_initialized = False


# ---------------------------------------------------------------------------
# Firebase Initialization
# ---------------------------------------------------------------------------

def init_firebase() -> bool:
    """Initialize Firebase Admin SDK. Idempotent — safe to call multiple times.

    Returns True if Firebase is ready, False if credentials are missing.
    """
    global _firebase_initialized
    if _firebase_initialized:
        return True

    try:
        import firebase_admin
        from firebase_admin import credentials

        # Check if already initialized by another module
        try:
            firebase_admin.get_app()
            _firebase_initialized = True
            return True
        except ValueError:
            pass

        from app.config import FIREBASE_CREDENTIALS_PATH

        if not FIREBASE_CREDENTIALS_PATH:
            logger.warning(
                "[FCM] FIREBASE_CREDENTIALS_PATH not set. "
                "Push notifications are disabled."
            )
            return False

        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        logger.info("[FCM] Firebase initialized successfully")
        print("[FCM] Firebase initialized -- push notifications enabled")
        return True

    except ImportError:
        logger.warning(
            "[FCM] firebase-admin not installed. "
            "Run: pip install firebase-admin"
        )
        return False
    except Exception as e:
        logger.error(f"[FCM] Firebase initialization failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Notification Sending
# ---------------------------------------------------------------------------

async def notify_caregivers(
    caregivers: list[dict],
    elder_name: str,
    report_type: str,
    report_id: str,
    report_summary: str = "",
    elder_user_id: str = "",
) -> dict:
    """Send push notification to all linked caregivers.

    Args:
        caregivers: List of caregiver dicts from user:caregivers session state.
                    Each must have at least 'fcm_token'.
        elder_name: Elder's display name (for notification title).
        report_type: 'emergency', 'daily', 'weekly', or 'monthly'.
        report_id: The generated report's ID (for deep linking).
        report_summary: Brief summary text for notification body.
        elder_user_id: Elder's user_id (for the data payload).

    Returns:
        dict with 'sent', 'failed', and 'details' keys.
    """
    if not caregivers:
        logger.info("[FCM] No caregivers to notify")
        return {"sent": 0, "failed": 0, "details": []}

    if not init_firebase():
        logger.warning("[FCM] Firebase not initialized — skipping notifications")
        return {"sent": 0, "failed": 0, "details": ["firebase_not_initialized"]}

    try:
        from firebase_admin import messaging
    except ImportError:
        return {"sent": 0, "failed": 0, "details": ["firebase_admin_not_installed"]}

    # Build notification content based on report type
    title, body, priority = _build_notification_content(
        elder_name=elder_name,
        report_type=report_type,
        report_summary=report_summary,
    )

    sent = 0
    failed = 0
    details = []

    for caregiver in caregivers:
        fcm_token = caregiver.get("fcm_token")
        if not fcm_token:
            details.append({
                "caregiver": caregiver.get("name", "unknown"),
                "status": "skipped",
                "reason": "no_fcm_token",
            })
            continue

        try:
            # Build the FCM message
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data={
                    "type": f"{report_type}_report",
                    "report_id": report_id,
                    "elder_user_id": elder_user_id,
                    "report_type": report_type,
                    "click_action": "OPEN_REPORT",
                },
                token=fcm_token,
                android=messaging.AndroidConfig(
                    priority="high" if priority == "urgent" else "normal",
                    notification=messaging.AndroidNotification(
                        click_action="OPEN_REPORT",
                        priority="max" if priority == "urgent" else "default",
                    ),
                ),
                apns=messaging.APNSConfig(
                    headers={"apns-priority": "10" if priority == "urgent" else "5"},
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            alert=messaging.ApsAlert(
                                title=title,
                                body=body,
                            ),
                            sound="default",
                            badge=1,
                        ),
                    ),
                ),
            )

            # Send the message
            response = messaging.send(message)

            sent += 1
            details.append({
                "caregiver": caregiver.get("name", "unknown"),
                "status": "sent",
                "message_id": response,
            })
            logger.info(
                f"[FCM] ✅ Notification sent to {caregiver.get('name', 'unknown')} "
                f"for elder {elder_name} ({report_type})"
            )

        except messaging.UnregisteredError:
            # Token is invalid (app uninstalled, token expired)
            failed += 1
            details.append({
                "caregiver": caregiver.get("name", "unknown"),
                "status": "failed",
                "reason": "token_expired",
            })
            logger.warning(
                f"[FCM] Token expired for {caregiver.get('name', 'unknown')}. "
                f"Caregiver needs to re-register."
            )

        except Exception as e:
            failed += 1
            details.append({
                "caregiver": caregiver.get("name", "unknown"),
                "status": "failed",
                "reason": str(e),
            })
            logger.error(
                f"[FCM] Failed to notify {caregiver.get('name', 'unknown')}: {e}"
            )

    result = {"sent": sent, "failed": failed, "details": details}
    print(
        f"[FCM] Notification summary for {elder_name} ({report_type}): "
        f"{sent} sent, {failed} failed"
    )
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_notification_content(
    elder_name: str,
    report_type: str,
    report_summary: str = "",
) -> tuple[str, str, str]:
    """Build notification title, body, and priority based on report type.

    Returns:
        Tuple of (title, body, priority).
        Priority is 'urgent' for emergencies, 'normal' for others.
    """
    if report_type == "emergency":
        title = f"🚨 حالة طوارئ — {elder_name}"
        body = report_summary or f"تم رصد حالة طوارئ لـ {elder_name}. اطلع على التقرير فوراً."
        priority = "urgent"

    elif report_type == "daily":
        title = f"📋 تقرير يومي — {elder_name}"
        body = report_summary or f"التقرير اليومي لـ {elder_name} جاهز. اطلع عليه."
        priority = "normal"

    elif report_type == "weekly":
        title = f"📊 تقرير أسبوعي — {elder_name}"
        body = report_summary or f"التقرير الأسبوعي لـ {elder_name} جاهز."
        priority = "normal"

    elif report_type == "monthly":
        title = f"📈 تقرير شهري — {elder_name}"
        body = report_summary or f"التقرير الشهري لـ {elder_name} جاهز."
        priority = "normal"

    else:
        title = f"📋 تقرير صحي — {elder_name}"
        body = report_summary or f"تقرير صحي جديد لـ {elder_name}."
        priority = "normal"

    return title, body, priority
