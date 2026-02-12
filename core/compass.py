from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import threading


Axis = Literal["platform", "director", "style"]
AxisOrAll = Literal["platform", "director", "style", "all"]


@dataclass(frozen=True)
class CompassDoc:
    axis: Axis
    name: str
    alias: str | None
    description: str | None
    version: str | None
    last_updated: str | None
    author: str | None
    body: str
    source_path: Path


@dataclass(frozen=True)
class CompassSelection:
    director: str | None = None
    style: list[str] | None = None

    def __str__(self) -> str:
        parts = []

        if self.director:
            parts.append(f"director={self.director}")

        if self.style:
            parts.append(f"style={', '.join(self.style)}")

        return "CompassSelection(" + ", ".join(parts) + ")"


def _parse_frontmatter(md_text: str) -> tuple[dict[str, str], str]:
    lines = md_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, md_text

    meta: dict[str, str] = {}
    i = 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            body = "\n".join(lines[i + 1 :]).lstrip("\n")
            return meta, body
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
        i += 1

    return {}, md_text


def _axis_dir(axis: Axis) -> str:
    if axis == "platform":
        return "platform"
    if axis == "director":
        return "director"
    return "style"


def _choice_id_from_path(*, axis_path: Path, file_path: Path) -> str | None:
    # expects: {id}_compass.md (id may include subfolders)
    if not file_path.name.endswith("_compass.md"):
        return None

    rel = file_path.relative_to(axis_path).as_posix()
    return rel[: -len("_compass.md")]


class CompassRegistry:
    def __init__(self, *, root_dir: str | Path = "./compass"):
        self.root_dir = Path(root_dir)
        self._lock = threading.RLock()
        self._docs: dict[tuple[Axis, str], CompassDoc] = {}
        self._mtimes: dict[tuple[Axis, str], float] = {}

    def set_root_dir(self, root_dir: str | Path) -> None:
        with self._lock:
            self.root_dir = Path(root_dir)
            self._docs.clear()
            self._mtimes.clear()

    def list_choices(self, axis: Axis) -> list[str]:
        axis_path = self.root_dir / _axis_dir(axis)
        if not axis_path.exists() or not axis_path.is_dir():
            return []

        names: list[str] = []
        for p in axis_path.rglob("*_compass.md"):
            if not p.is_file():
                continue
            n = _choice_id_from_path(axis_path=axis_path, file_path=p)
            if n:
                names.append(n)
        names.sort()
        return names

    def list_all_choices(self) -> dict[Axis, list[str]]:
        return {
            "platform": self.list_choices("platform"),
            "director": self.list_choices("director"),
            "style": self.list_choices("style"),
        }

    def list_choice_cards(self, axis: Axis) -> list[dict[str, str]]:
        cards: list[dict[str, str]] = []
        for choice in self.list_choices(axis):
            doc = self.load_doc(axis=axis, name=choice)
            cards.append(
                {
                    "axis": axis,
                    "id": choice,
                    "name": doc.name,
                    "alias": doc.alias or "",
                    "description": doc.description or "",
                }
            )
        return cards

    def list_all_choice_cards(self) -> dict[Axis, list[dict[str, str]]]:
        return {
            "platform": self.list_choice_cards("platform"),
            "director": self.list_choice_cards("director"),
            "style": self.list_choice_cards("style"),
        }

    def _doc_path(self, *, axis: Axis, name: str) -> Path:
        # name may include subfolders like "tutorial/review"
        return self.root_dir / _axis_dir(axis) / Path(f"{name}_compass.md")

    def resolve_choice_id(self, *, axis: Axis, query: str) -> str | None:
        q = (query or "").strip()
        if not q:
            return None

        q_cf = q.casefold()
        # Fast path: exact id match
        if q in self.list_choices(axis):
            return q

        for choice in self.list_choices(axis):
            try:
                doc = self.load_doc(axis=axis, name=choice)
            except FileNotFoundError:
                continue

            if doc.name and doc.name.strip().casefold() == q_cf:
                return choice

            if doc.alias:
                # allow alias values like "张艺谋" or "总导演 / 通用导演"
                for a in doc.alias.replace("，", ",").replace("/", ",").split(","):
                    a = a.strip()
                    if a and a.casefold() == q_cf:
                        return choice

        return None

    def load_doc(self, *, axis: Axis, name: str) -> CompassDoc:
        p = self._doc_path(axis=axis, name=name)
        if not p.exists():
            raise FileNotFoundError(f"Compass doc not found: {p}")

        mtime = p.stat().st_mtime
        key = (axis, name)

        with self._lock:
            cached_mtime = self._mtimes.get(key)
            if cached_mtime is not None and cached_mtime == mtime:
                cached = self._docs.get(key)
                if cached is not None:
                    return cached

            text = p.read_text(encoding="utf-8")
            meta, body = _parse_frontmatter(text)

            description = meta.get("description")
            if not description:
                # Fallback: use first non-empty markdown heading line as description.
                for ln in body.splitlines():
                    s = ln.strip()
                    if not s:
                        continue
                    if s.startswith("#"):
                        description = s.lstrip("#").strip()
                        break
                if not description:
                    description = meta.get("name", name)

            doc = CompassDoc(
                axis=axis,
                name=meta.get("name", name),
                alias=meta.get("alias"),
                description=description,
                version=meta.get("version"),
                last_updated=meta.get("last_updated"),
                author=meta.get("author"),
                body=body.strip(),
                source_path=p,
            )
            self._docs[key] = doc
            self._mtimes[key] = mtime
            return doc

    def reload(self) -> None:
        with self._lock:
            self._docs.clear()
            self._mtimes.clear()


_COMPASS_SINGLETON: CompassRegistry | None = None
_SINGLETON_LOCK = threading.Lock()


def get_compass(*, root_dir: str | Path = "./compass") -> CompassRegistry:
    global _COMPASS_SINGLETON
    if _COMPASS_SINGLETON is None:
        with _SINGLETON_LOCK:
            if _COMPASS_SINGLETON is None:
                _COMPASS_SINGLETON = CompassRegistry(root_dir=root_dir)
    # If caller passes a different root_dir, we switch root (and clear caches)
    if Path(root_dir) != _COMPASS_SINGLETON.root_dir:
        _COMPASS_SINGLETON.set_root_dir(root_dir)
    return _COMPASS_SINGLETON


def list_compass_choices(
    *,
    axis: AxisOrAll,
    root_dir: str | Path = "./compass",
) -> list[str] | dict[Axis, list[str]]:
    compass = get_compass(root_dir=root_dir)
    if axis == "all":
        return compass.list_all_choices()
    return compass.list_choices(axis)  # type: ignore[arg-type]


def list_compass_choice_cards(
    *,
    axis: AxisOrAll,
    root_dir: str | Path = "./compass",
) -> list[dict[str, str]] | dict[Axis, list[dict[str, str]]]:
    compass = get_compass(root_dir=root_dir)
    if axis == "all":
        return compass.list_all_choice_cards()
    return compass.list_choice_cards(axis)  # type: ignore[arg-type]


def load_compass_doc(*, root_dir: str | Path, axis: Axis, name: str) -> CompassDoc:
    compass = get_compass(root_dir=root_dir)
    try:
        return compass.load_doc(axis=axis, name=name)
    except FileNotFoundError:
        resolved = compass.resolve_choice_id(axis=axis, query=name)
        if resolved and resolved != name:
            return compass.load_doc(axis=axis, name=resolved)
        raise


def build_compass_prompt(
    *,
    root_dir: str | Path,
    platform: str | None = None,
    selection: CompassSelection | None,
) -> str:
    if selection is None and not platform:
        return ""

    parts: list[str] = []

    if platform:
        try:
            doc = load_compass_doc(root_dir=root_dir, axis="platform", name=platform)
            parts.append(doc.body)
        except FileNotFoundError:
            pass

    if selection is not None and selection.director:
        doc = load_compass_doc(root_dir=root_dir, axis="director", name=selection.director)
        parts.append(doc.body)

    if selection is not None and selection.style:
        for s in selection.style:
            doc = load_compass_doc(root_dir=root_dir, axis="style", name=s)
            parts.append(doc.body)

    if not parts:
        return ""

    return "\n\n".join(parts).strip() + "\n"
