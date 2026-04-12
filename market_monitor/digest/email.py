"""Email sender - send digest via gws (googleworkspace CLI)."""

import base64
import subprocess
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from ..config import Config

GWS_BIN = "googleworkspace"


def _encode_message(to: str, subject: str, body: str, html: bool = False) -> str:
    """Build a MIME message and return base64url-encoded raw string for Gmail API."""
    msg = MIMEMultipart("alternative")
    msg["To"] = to
    msg["Subject"] = subject

    if html:
        msg.attach(MIMEText(body, "html", "utf-8"))
    else:
        msg.attach(MIMEText(body, "plain", "utf-8"))

    raw_bytes = msg.as_bytes()
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii")


@dataclass
class EmailSender:
    """Send emails via gws (googleworkspace CLI)."""

    recipient: str
    subject: str = "Market Digest"

    def __init__(self, config: Config, recipient: str, subject: str = "Market Digest"):
        self.recipient = recipient
        self.subject = subject

    def send(self, body: str, html: bool = False) -> bool:
        """
        Send email via gws CLI.

        Args:
            body: Email body text
            html: If True, send as HTML

        Returns:
            True if sent successfully, False otherwise
        """
        raw = _encode_message(self.recipient, self.subject, body, html)

        cmd = [
            GWS_BIN, "gmail", "users", "messages", "send",
            "--params", '{"userId": "me"}',
            "--json", f'{{"raw": "{raw}"}}',
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                print(f"[Email] gws send failed: {result.stderr}")
                return False

            print(f"[Email] Sent to {self.recipient}")
            return True

        except FileNotFoundError:
            print("[Email] googleworkspace command not found")
            return False
        except subprocess.TimeoutExpired:
            print("[Email] gws send timed out")
            return False
        except Exception as e:
            print(f"[Email] Error: {e}")
            return False
