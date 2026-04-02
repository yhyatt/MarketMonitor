"""Send digest via Telegram using openclaw CLI or direct HTTP fallback."""

import os
import subprocess
import urllib.parse
import urllib.request
import json


def send_telegram(chat_id: str, message: str) -> bool:
    """Send message via Telegram. Uses openclaw message tool or direct bot API."""
    # Try openclaw message tool first
    try:
        result = subprocess.run(
            ["openclaw", "message", "send", "telegram", chat_id, message],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print(f"[Telegram] Sent to {chat_id} via openclaw")
            return True
    except Exception:
        pass

    # Fallback: direct Telegram bot API via env var
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        # Try reading from openclaw .env
        env_path = os.path.expanduser("~/.openclaw/.env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("TELEGRAM_BOT_TOKEN="):
                        bot_token = line.split("=", 1)[1].strip().strip('"')
                        break

    if not bot_token:
        print("[Telegram] Error: No TELEGRAM_BOT_TOKEN available")
        return False

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = json.dumps({
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": False,
        }).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                print(f"[Telegram] Sent to {chat_id} via bot API")
                return True
            print(f"[Telegram] API error: {result}")
            return False
    except Exception as e:
        print(f"[Telegram] Error: {e}")
        return False


class TelegramSender:
    """Class wrapper for Telegram delivery (used by formatter and tests)."""

    def __init__(self, config=None):
        self.config = config

    def send(self, chat_id: str, message: str) -> bool:
        """Send a message to a Telegram chat."""
        return send_telegram(chat_id, message)

    def send_digest(self, chat_id: str, message: str) -> bool:
        """Send digest, splitting into chunks if over Telegram's 4096-char limit."""
        LIMIT = 4000
        if len(message) <= LIMIT:
            return self.send(chat_id, message)

        # Split on double newlines (paragraph boundaries) to keep chunks readable
        chunks = []
        current = ""
        for para in message.split("\n\n"):
            candidate = (current + "\n\n" + para).strip() if current else para
            if len(candidate) <= LIMIT:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                # If single para is too long, hard-split it
                if len(para) > LIMIT:
                    for i in range(0, len(para), LIMIT):
                        chunks.append(para[i:i+LIMIT])
                else:
                    current = para

        if current:
            chunks.append(current)

        success = True
        for i, chunk in enumerate(chunks):
            prefix = f"({i+1}/{len(chunks)}) " if len(chunks) > 1 else ""
            if not self.send(chat_id, prefix + chunk):
                success = False
        return success
