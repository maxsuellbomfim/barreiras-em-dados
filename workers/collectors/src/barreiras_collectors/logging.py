"""Eventos JSON pequenos, sem corpo de resposta ou dados pessoais."""

from __future__ import annotations

import json
import logging
from typing import Any


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    **fields: Any,
) -> None:
    payload = {"event": event, **fields}
    logger.log(
        level,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
    )
