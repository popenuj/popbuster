from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AppConfig:
    commercials_enabled: bool = True
    opening_jingle_enabled: bool = True


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return AppConfig()

        return AppConfig(
            commercials_enabled=bool(raw.get("commercials_enabled", True)),
            opening_jingle_enabled=bool(raw.get("opening_jingle_enabled", True)),
        )

    def save(self, config: AppConfig) -> None:
        self.path.write_text(
            json.dumps(asdict(config), indent=2, sort_keys=True),
            encoding="utf-8",
        )
