"""Email sender - send digest via gog gmail."""

import subprocess
from dataclasses import dataclass
from typing import Optional

from ..config import Config


@dataclass
class EmailSender:
    """Send emails via gog gmail integration."""

    config: Config
    sender_account: str = "hyatt.yonatan@gmail.com"

    def send(
        self,
        to: str,
        subject: str,
        body_html: str,
        body_plain: str,
    ) -> bool:
        """Send email via gog gmail.

        Args:
            to: Recipient email address
            subject: Email subject
            body_html: HTML body
            body_plain: Plain text body

        Returns:
            True if sent successfully
        """
        if not self.config.gog_keyring_password:
            print("[Email] Warning: GOG_KEYRING_PASSWORD not set, skipping")
            return False

        cmd = [
            "gog", "gmail", "send",
            "--to", to,
            "--subject", subject,
            "--body-html", body_html,
            "--body", body_plain,
            "--force",
            "--account", self.sender_account,
        ]

        env = {"GOG_KEYRING_PASSWORD": self.config.gog_keyring_password}

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                env={**subprocess.os.environ, **env},
            )

            if result.returncode != 0:
                print(f"[Email] Error: {result.stderr}")
                return False

            print(f"[Email] Sent to {to}")
            return True

        except subprocess.TimeoutExpired:
            print("[Email] Command timed out")
            return False
        except FileNotFoundError:
            print("[Email] gog command not found")
            return False
        except Exception as e:
            print(f"[Email] Error: {e}")
            return False

    def send_digest(
        self,
        to: str,
        subject: str,
        html: str,
        plain: str,
    ) -> bool:
        """Send formatted digest email.

        Args:
            to: Recipient email address
            subject: Email subject
            html: HTML content
            plain: Plain text content

        Returns:
            True if sent successfully
        """
        return self.send(to, subject, html, plain)
