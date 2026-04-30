import httpx
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

async def send_discord_alert(message: str):
    """Send a message to Discord via webhook. Fire-and-forget."""
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                DISCORD_WEBHOOK_URL,
                json={"content": message},
                timeout=5
            )
    except Exception as e:
        print(f"[DISCORD] Failed to send alert: {e}")

def send_discord_alert_sync(message: str):
    """Synchronous version for use inside paper_trader.py's blocking loop."""
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        import httpx
        with httpx.Client() as client:
            client.post(
                DISCORD_WEBHOOK_URL,
                json={"content": message},
                timeout=5
            )
    except Exception as e:
        print(f"[DISCORD] Failed to send alert: {e}")
