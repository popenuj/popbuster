from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Tape:
    id: str
    title: str
    collection: str
    video_path: Path


class TapeCatalog:
    def __init__(self, tapes: Iterable[Tape]) -> None:
        self._tapes = {tape.id: tape for tape in tapes}

    @classmethod
    def from_json(cls, path: Path) -> "TapeCatalog":
        project_root = path.parent.parent
        raw_tapes = json.loads(path.read_text(encoding="utf-8"))
        tapes: list[Tape] = []
        for raw in raw_tapes:
            video_path = Path(raw["video_path"])
            if not video_path.is_absolute():
                video_path = (project_root / video_path).resolve()
            tapes.append(
                Tape(
                    id=raw["id"],
                    title=raw["title"],
                    collection=raw["collection"],
                    video_path=video_path,
                )
            )
        return cls(tapes)

    def get(self, tape_id: str) -> Tape | None:
        return self._tapes.get(tape_id)

    def first_available(self) -> Tape | None:
        for tape in self._tapes.values():
            if tape.video_path.exists():
                return tape
        return next(iter(self._tapes.values()), None)

    def available(self) -> list[Tape]:
        return [tape for tape in self._tapes.values() if tape.video_path.exists()]
