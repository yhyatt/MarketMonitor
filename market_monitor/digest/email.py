"""Email sender - send digest via gog CLI."""

import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

from ..config import Config

GOG_BIN = "/home/openclaw/.local/bin/gog"
GOG_KEYRING_PASSWORD = "kai-gog-keyring"
DEFAULT_ACCOUNT = "amisraelk@gmail.com"


@dataclass
class EmailSender:
    """Send emails via gog CLI."""

    recipient: str
    subject: str = "Market Digest"

    def __init__(self, config: Config, recipient: str, subject: str = "Market Digest"):
        self.recipient = recipient
        self.subject = subject

    def send(self, body: str, html: bool = False) -> bool:
        """
        Send email via gog CLI.

        Args:
            body: Email body text
            html: If True, send as HTML

        Returns:
            True if sent successfully, False otherwise
        """
        env = {**os.environ, "GOG_KEYRING_PASSWORD": GOG_KEYRING_PASSWORD}

        try:
            if html:
                # Write HTML to temp file to avoid CLI arg length limits
                with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                    f.write(body)
                    html_path = f.name

                try:
                    result = subprocess.run(
                        [
                            GOG_BIN, "gmail", "send",
                            "-a", DEFAULT_ACCOUNT,
                            "--to", self.recipient,
                            "--subject", self.subject,
                            "--body-html", body,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        env=env,
                    )
                finally:
                    os.unlink(html_path)
            else:
                result = subprocess.run(
                    [
                        GOG_BIN, "gmail", "send",
                        "-a", DEFAULT_ACCOUNT,
                        "--to", self.recipient,
                        "--subject", self.subject,
                        "--body", body,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=env,
                )

            if result.returncode != 0:
                print(f"[Email] gog send failed: {result.stderr}")
                return False

            print(f"[Email] Sent to {self.recipient}")
            return True

        except FileNotFoundError:
            print("[Email] gog command not found")
            return False
        except subprocess.TimeoutExpired:
            print("[Email] gog send timed out")
            return False
        except Exception as e:
            print(f"[Email] Error: {e}")
            return False
