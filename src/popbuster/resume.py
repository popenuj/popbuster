from __future__ import annotations

import json
from pathlib import Path


class ResumeStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_ms(self, tape_id: str) -> int:
        return int(self._read().get(tape_id, 0))

    def save_ms(self, tape_id: str, position_ms: int) -> None:
        data = self._read()
        data[tape_id] = max(0, int(position_ms))
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def clear(self, tape_id: str) -> None:
        data = self._read()
        if tape_id in data:
            del data[tape_id]
            self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def _read(self) -> dict[str, int]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return {str(key): int(value) for key, value in raw.items()}
