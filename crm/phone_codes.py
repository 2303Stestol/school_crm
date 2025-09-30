from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.utils import timezone


def append_phone_code(phone_number: str, code: str, reason: str) -> None:
    """Append a phone verification code entry to the configured log file."""

    path = Path(settings.VERIFICATION_CODES_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = timezone.now().isoformat()
    line = f"{timestamp}\t{reason}\t{phone_number}\t{code}\n"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line)
