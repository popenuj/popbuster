from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml


FILTER_FIELDS = {
    "people": "People",
    "locations": "Places",
    "media_type": "Media type",
    "occasions": "Occasion",
    "year": "Year",
    "pets": "Pets",
}


@dataclass(frozen=True)
class Tape:
    id: str
    title: str
    collection: str
    video_path: Path
    media_type: str = "home_video"
    tape_id: str | None = None
    year: int | None = None
    tape_name: str | None = None
    recapture: bool = False
    people: tuple[str, ...] = field(default_factory=tuple)
    locations: tuple[str, ...] = field(default_factory=tuple)
    occasions: tuple[str, ...] = field(default_factory=tuple)
    pets: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TapeDefinition:
    id: str
    title: str
    source_type: str
    filters: dict[str, tuple[Any, ...]]


@dataclass(frozen=True)
class FilterValue:
    id: str
    title: str
    count: int


@dataclass(frozen=True)
class FilterCategory:
    id: str
    title: str
    values: tuple[FilterValue, ...]


class TapeCatalog:
    def __init__(
        self,
        tapes: Iterable[Tape],
        tape_definitions: Iterable[TapeDefinition] = (),
        display_names: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self._tapes = {tape.id: tape for tape in tapes}
        self._tape_definitions = {tape.id: tape for tape in tape_definitions}
        self._display_names = display_names or {}

    @classmethod
    def from_library(cls, library_dir: Path) -> "TapeCatalog":
        project_root = library_dir.parent
        raw_videos = _read_yaml(library_dir / "videos.yml").get("videos", [])
        raw_tapes = _read_yaml(library_dir / "tapes.yml").get("tapes", [])
        display_names = {
            "people": _read_display_names(library_dir / "people.yml", "people"),
            "locations": _read_display_names(library_dir / "locations.yml", "locations"),
            "occasions": _read_display_names(library_dir / "occasions.yml", "occasions"),
            "pets": _read_display_names(library_dir / "pets.yml", "pets"),
        }

        tapes = [
            _video_to_tape(raw_video, project_root)
            for raw_video in raw_videos
        ]
        tape_definitions = [
            TapeDefinition(
                id=str(raw_tape["id"]),
                title=str(raw_tape["title"]),
                source_type=str(raw_tape.get("source_type", "curated")),
                filters=_normalize_filters(raw_tape.get("filters", {})),
            )
            for raw_tape in raw_tapes
        ]
        return cls(tapes, tape_definitions, display_names)

    def get(self, tape_id: str) -> Tape | None:
        queue = self.queue_for_tape(tape_id)
        return queue[0] if queue else None

    def queue_for_tape(self, tape_id: str) -> list[Tape]:
        if tape_id in self._tapes:
            tape = self._tapes[tape_id]
            return [tape] if tape.video_path.exists() else []

        tape_definition = self._tape_definitions.get(tape_id)
        if tape_definition is None:
            return []
        if not tape_definition.filters:
            return [tape for tape in self.available() if tape.tape_id == tape_id]
        return self.filter_videos(tape_definition.filters)

    def first_available(self) -> Tape | None:
        for tape in self._tapes.values():
            if tape.video_path.exists():
                return tape
        return next(iter(self._tapes.values()), None)

    def available(self) -> list[Tape]:
        return [tape for tape in self._tapes.values() if tape.video_path.exists()]

    def filter_videos(self, filters: dict[str, tuple[Any, ...]]) -> list[Tape]:
        filters = _normalize_filters(filters)
        return [
            tape
            for tape in self.available()
            if _matches_filters(tape, filters)
        ]

    def filter_categories(self) -> tuple[FilterCategory, ...]:
        categories: list[FilterCategory] = []
        for field_name, title in FILTER_FIELDS.items():
            counts: dict[Any, int] = {}
            for tape in self.available():
                for value in _field_values(tape, field_name):
                    counts[value] = counts.get(value, 0) + 1
            values = tuple(
                FilterValue(
                    id=str(value),
                    title=self._display_title(field_name, value),
                    count=count,
                )
                for value, count in sorted(counts.items(), key=lambda item: str(item[0]))
            )
            if values:
                categories.append(FilterCategory(id=field_name, title=title, values=values))
        return tuple(categories)

    def _display_title(self, field_name: str, value: Any) -> str:
        if field_name == "year":
            return str(value)
        if field_name == "media_type":
            return str(value).replace("_", " ").title()
        return self._display_names.get(field_name, {}).get(
            str(value),
            str(value).replace("_", " ").title(),
        )


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_display_names(path: Path, root_key: str) -> dict[str, str]:
    raw_items = _read_yaml(path).get(root_key, {})
    return {
        str(item_id): _display_name_from_lookup(item_id, raw_item)
        for item_id, raw_item in raw_items.items()
    }


def _display_name_from_lookup(item_id: Any, raw_item: Any) -> str:
    if isinstance(raw_item, dict):
        return str(raw_item.get("display_name", item_id))
    return str(raw_item)


def _video_to_tape(raw: dict[str, Any], project_root: Path) -> Tape:
    video_path = Path(raw["file"])
    if not video_path.is_absolute():
        video_path = (project_root / video_path).resolve()

    return Tape(
        id=str(raw["id"]),
        title=str(raw["title"]),
        collection=str(raw.get("collection", raw.get("media_type", "Home Videos"))),
        video_path=video_path,
        media_type=str(raw.get("media_type", "home_video")),
        tape_id=_optional_string(raw.get("tape_id")),
        year=_optional_int(raw.get("year")),
        tape_name=_optional_string(raw.get("tape_name")),
        recapture=bool(raw.get("recapture", False)),
        people=_string_tuple(raw.get("people", ())),
        locations=_string_tuple(raw.get("locations", ())),
        occasions=_string_tuple(raw.get("occasions", raw.get("categories", ()))),
        pets=_string_tuple(raw.get("pets", ())),
        tags=_string_tuple(raw.get("tags", ())),
    )


def _normalize_filters(raw_filters: dict[str, Any]) -> dict[str, tuple[Any, ...]]:
    return {
        str(field_name): tuple(_coerce_filter_value(value) for value in _as_list(values))
        for field_name, values in raw_filters.items()
    }


def _coerce_filter_value(value: Any) -> Any:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return str(value)


def _matches_filters(tape: Tape, filters: dict[str, tuple[Any, ...]]) -> bool:
    for field_name, wanted_values in filters.items():
        tape_values = set(_field_values(tape, field_name))
        if not tape_values.intersection(wanted_values):
            return False
    return True


def _field_values(tape: Tape, field_name: str) -> tuple[Any, ...]:
    value = getattr(tape, field_name)
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    return (value,)


def _string_tuple(values: Any) -> tuple[str, ...]:
    return tuple(str(value) for value in _as_list(values))


def _as_list(values: Any) -> list[Any]:
    if values is None:
        return []
    if isinstance(values, list):
        return values
    if isinstance(values, tuple):
        return list(values)
    return [values]


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
