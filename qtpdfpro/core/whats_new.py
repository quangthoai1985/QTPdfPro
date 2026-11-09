"""Ghi chú «Có gì mới» cho người dùng: đọc tệp đi kèm ứng dụng và quyết định hiện bản nào.

Thuần Python (không Qt) — hộp thoại nằm ở `ui/whats_new_dialog.py`. So sánh phiên bản dùng lại
`update_check.parse_version`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from qtpdfpro.core.update_check import parse_version

NOTES_FILE = Path(__file__).resolve().parents[1] / "ui" / "assets" / "whats_new.json"


@dataclass(frozen=True)
class NoteItem:
    icon: str
    title: str
    text: str
    shortcut: str = ""


@dataclass(frozen=True)
class VersionNotes:
    version: str
    date: str
    headline: str
    items: tuple[NoteItem, ...]


def _parse_version_entry(raw: object) -> VersionNotes | None:
    if not isinstance(raw, dict) or parse_version(str(raw.get("version", ""))) is None:
        return None
    items: list[NoteItem] = []
    for it in raw.get("items") or []:
        if not isinstance(it, dict) or not it.get("title"):
            return None
        items.append(NoteItem(str(it.get("icon", "")), str(it["title"]), str(it.get("text", "")),
                              str(it.get("shortcut", ""))))
    return VersionNotes(str(raw["version"]), str(raw.get("date", "")), str(raw.get("headline", "")), tuple(items))


def load_notes(path: Path | None = None) -> list[VersionNotes]:
    """Đọc ghi chú, mới nhất trước. Tệp thiếu / hỏng / sai cấu trúc → `[]` (không làm hỏng khởi động)."""
    try:
        data = json.loads((path or NOTES_FILE).read_text(encoding="utf-8-sig"))
        versions = data["versions"]
        if not isinstance(versions, list):
            return []
        notes = [_parse_version_entry(v) for v in versions]
    except Exception:
        return []
    if any(n is None for n in notes):
        return []
    result = [n for n in notes if n is not None]
    result.sort(key=lambda n: parse_version(n.version), reverse=True)  # type: ignore[arg-type,return-value]
    return result


def notes_for(version: str, notes: list[VersionNotes]) -> VersionNotes | None:
    target = parse_version(version)
    if target is None:
        return None
    for n in notes:
        if parse_version(n.version) == target:
            return n
    return None


def notes_to_show(current: str, last_seen: str, settings_existed: bool, notes: list[VersionNotes]) -> list[VersionNotes]:
    """Các ghi chú cần hiện lúc khởi động (mới nhất trước)."""
    cur = parse_version(current)
    if cur is None:
        return []
    seen = parse_version(last_seen) if last_seen else None
    if seen is None:
        if not settings_existed:
            return []  # cài mới
        found = notes_for(current, notes)
        return [found] if found else []
    if seen >= cur:
        return []
    picked = [n for n in notes if seen < parse_version(n.version) <= cur]  # type: ignore[operator]
    return sorted(picked, key=lambda n: parse_version(n.version), reverse=True)  # type: ignore[arg-type,return-value]
