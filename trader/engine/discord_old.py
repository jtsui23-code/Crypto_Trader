import httpx
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

def _build_payload(title: str, fields: list[dict], color: int, footer: str = "Paper Trading Engine") -> dict:
    """Build a Discord webhook embed payload."""
    return {
        "embeds": [{
            "title": title,
            "color": color,
            "fields": fields,
            "footer": {"text": footer},
        }]
    }

async def send_discord_alert(title: str, fields: list[dict], color: int):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(DISCORD_WEBHOOK_URL, json=_build_payload(title, fields, color), timeout=5)
    except Exception as e:
        print(f"[DISCORD] Failed to send alert: {e}")

def send_discord_alert_sync(title: str, fields: list[dict], color: int):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        with httpx.Client() as client:
            client.post(DISCORD_WEBHOOK_URL, json=_build_payload(title, fields, color), timeout=5)
    except Exception as e:
        print(f"[DISCORD] Failed to send alert: {e}")