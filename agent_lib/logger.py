"""Registro append-only de toda la sesión en conversation_log.csv.

Nunca se reescribe el archivo: cada evento se agrega como una fila nueva,
así el historial completo sobrevive a reinicios del agente.
"""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "conversation_log.csv"
FIELDNAMES = ["actor", "message", "tool_call", "timestamp"]


def _ensure_log() -> None:
    if LOG_PATH.exists():
        return
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def log_event(actor: str, message: Optional[str] = None, tool_call: Optional[Union[str, dict]] = None) -> None:
    """Agrega un evento al log. `tool_call`, si es un dict, se serializa a JSON."""
    _ensure_log()
    if isinstance(tool_call, dict):
        tool_call = json.dumps(tool_call, ensure_ascii=False)
    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "actor": actor,
                "message": message or "",
                "tool_call": tool_call or "",
            }
        )
