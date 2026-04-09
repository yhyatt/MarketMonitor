"""Email sender - send digest via googleworkspace CLI."""

import subprocess
from dataclasses import dataclass
from typing import Optional

from ..config import Config

GWS_BIN = "/usr/local/bin/googleworkspace"


@dataclass
class EmailSender:
    """Send emails via googleworkspace CLI."""

    recipient: str
    subject: str = "Market Digest"

    def __init__(self, config: Config):
        self.recipient = config.email_recipient
        self.subject = config.email_subject

    def send(self, body: str, html: bool = False) -> bool:
        """
        Send email via googleworkspace CLI.

        Args:
            body: Email body text
            html: If True, send as HTML

        Returns:
            True if sent successfully, False otherwise
        """
        cmd = [
            GWS_BIN, "gmail", "+send",
            "--to", self.recipient,
            "--subject", self.subject,
            "--body", body,
        ]
        if html:
            cmd.append("--html")

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
