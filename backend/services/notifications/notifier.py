"""
Multi-channel notifier: Twilio SMS + Resend Email.
Routes alerts based on enabled channels. Fails safe (logs-only) if keys missing.

Events that trigger notifications:
  - LIVE trade fill / close
  - Circuit breaker trip
  - Broker disconnection
  - Kitty low-balance warning (<$200 remaining)
"""
import os
import threading
import time
from typing import Optional
from core.logger import logger

# ── Configuration (from .env) ─────────────────────────────────────────────────
TWILIO_ACCOUNT_SID  = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN   = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_FROM_NUMBER  = os.environ.get("TWILIO_FROM_NUMBER", "").strip()
# Falls back to BOSS_PHONE in .env so Jason gets alerts automatically
ALERT_SMS_TO        = (os.environ.get("ALERT_SMS_TO", "") or os.environ.get("BOSS_PHONE", "")).strip()

RESEND_API_KEY      = os.environ.get("RESEND_API_KEY", "").strip()
RESEND_FROM_EMAIL   = os.environ.get("RESEND_FROM_EMAIL", "alerts@trading.local").strip()
# Falls back to BOSS_EMAIL in .env so Jason gets alerts automatically
ALERT_EMAIL_TO      = (os.environ.get("ALERT_EMAIL_TO", "") or os.environ.get("BOSS_EMAIL", "")).strip()

# Rate-limit: don't spam — same event-key deduped within window
_dedupe_lock = threading.Lock()
_last_sent = {}   # {event_key: timestamp}
_DEDUPE_WINDOW = 300  # 5 minutes


def _should_send(event_key: str) -> bool:
    with _dedupe_lock:
        now = time.time()
        last = _last_sent.get(event_key, 0)
        if now - last < _DEDUPE_WINDOW:
            return False
        _last_sent[event_key] = now
        return True


def sms_enabled() -> bool:
    return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER and ALERT_SMS_TO)


def email_enabled() -> bool:
    return bool(RESEND_API_KEY and ALERT_EMAIL_TO)


def _send_sms(body: str) -> bool:
    if not sms_enabled():
        logger.debug("SMS disabled (missing Twilio keys)")
        return False
    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = client.messages.create(to=ALERT_SMS_TO, from_=TWILIO_FROM_NUMBER, body=body[:1500])
        logger.info("SMS sent (sid=%s) to %s", msg.sid, ALERT_SMS_TO)
        return True
    except Exception as exc:
        logger.warning("Twilio SMS failed: %s", exc)
        return False


def _send_email(subject: str, body: str) -> bool:
    if not email_enabled():
        logger.debug("Email disabled (missing Resend keys)")
        return False
    try:
        import requests
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": RESEND_FROM_EMAIL,
                "to": [ALERT_EMAIL_TO],
                "subject": subject,
                "text": body,
            },
            timeout=10,
        )
        if resp.ok:
            logger.info("Email sent to %s: %s", ALERT_EMAIL_TO, subject)
            return True
        logger.warning("Resend email failed (%d): %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        logger.warning("Resend email failed: %s", exc)
        return False


def send(subject: str, body: str, event_key: Optional[str] = None,
         sms: bool = True, email: bool = True) -> dict:
    """
    Dispatch an alert to enabled channels.
    event_key: if provided, dedupes identical events within 5 min.
    Returns {'sms': bool, 'email': bool, 'skipped': bool}.
    """
    if event_key and not _should_send(event_key):
        return {"sms": False, "email": False, "skipped": True}

    # Run in a background thread so callers never block on network I/O
    def _dispatch():
        if sms and sms_enabled():
            _send_sms(f"[Trading] {subject}\n\n{body}")
        if email and email_enabled():
            _send_email(f"[Trading] {subject}", body)

    threading.Thread(target=_dispatch, daemon=True).start()

    return {
        "sms":     bool(sms and sms_enabled()),
        "email":   bool(email and email_enabled()),
        "skipped": False,
    }


def status() -> dict:
    """Return config status for the dashboard/settings UI."""
    return {
        "sms_enabled":   sms_enabled(),
        "email_enabled": email_enabled(),
        "sms_to":        ALERT_SMS_TO if sms_enabled() else None,
        "email_to":      ALERT_EMAIL_TO if email_enabled() else None,
    }
