"""Local store for resume points.

One JSON file per point, plus a small index. No database, no daemon, no
background process: a resume point is a file. That means you can copy it,
commit it, diff it, mail it, or delete it with ``rm``, and nothing else in the
system has to know.

Stability rules enforced here:

* every failure is raised as a :class:`~arova.resume.errors.ResumeError` with a
  hint, never as a bare ``OSError`` or ``JSONDecodeError``;
* the index is a *cache*, never the source of truth — if it is corrupt, stale,
  or missing, the store rebuilds it from the files on disk;
* an ambiguous reference is refused rather than guessed, because the cost of
  restoring the wrong point is higher than the cost of asking again.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

from arova.resume.errors import CorruptPointError, PointNotFound, StoreError
from arova.resume.schema import ResumePoint

ID_PATTERN = re.compile(r"^[0-9a-f]{8,32}$")
MIN_PREFIX = 2


def arova_home() -> str:
    return os.environ.get("AROVA_HOME") or os.path.join(os.path.expanduser("~"), ".arova")


def points_dir() -> str:
    path = os.path.join(arova_home(), "resume", "points")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exc:
        raise StoreError(
            f"cannot create the resume point store at {path}: {exc}",
            hint="set AROVA_HOME to a writable directory, e.g. AROVA_HOME=/tmp/arova",
        ) from exc
    return path


def index_path() -> str:
    path = os.path.join(arova_home(), "resume", "index.json")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError as exc:
        raise StoreError(f"cannot create the store index directory: {exc}") from exc
    return path


# ---------------------------------------------------------------------------
# low level
# ---------------------------------------------------------------------------

def _atomic_write(path: str, text: str) -> None:
    directory = os.path.dirname(path)
    try:
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    except OSError as exc:
        raise StoreError(
            f"cannot write to {directory}: {exc}",
            hint="set AROVA_HOME to a writable directory, or free up disk space",
        ) from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError as exc:
        raise StoreError(f"cannot write {path}: {exc}") from exc
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _read_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise PointNotFound(f"no resume point file at {path}") from exc
    except json.JSONDecodeError as exc:
        raise CorruptPointError(
            f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno})",
            hint=f"delete it with `rm {path}`, or restore it from a backup",
        ) from exc
    except OSError as exc:
        raise StoreError(f"cannot read {path}: {exc}") from exc


def _load_file(path: str) -> ResumePoint:
    data = _read_json(path)
    try:
        return ResumePoint.from_dict(data)
    except (ValueError, TypeError, KeyError) as exc:
        raise CorruptPointError(
            f"{path} is not a valid resume point: {exc}",
            hint=f"delete it with `rm {path}` if it is stale or damaged",
        ) from exc


def _point_files() -> Dict[str, str]:
    """id -> path, read from disk. The directory is the source of truth."""
    directory = points_dir()
    found: Dict[str, str] = {}
    try:
        names = os.listdir(directory)
    except OSError as exc:
        raise StoreError(f"cannot list {directory}: {exc}") from exc
    for name in names:
        if name.endswith(".json"):
            found[name[:-5]] = os.path.join(directory, name)
    return found


def _read_index() -> List[Dict[str, Any]]:
    try:
        data = _read_json(index_path())
    except PointNotFound:
        return []
    except StoreError:
        # A damaged index is a cache miss, not a failure: rebuild from disk.
        return []
    if not isinstance(data, list):
        return []
    return [entry for entry in data if isinstance(entry, dict) and entry.get("id")]


def _write_index(entries: List[Dict[str, Any]]) -> None:
    entries = sorted(entries, key=lambda e: e.get("created_at", 0), reverse=True)
    _atomic_write(index_path(), json.dumps(entries, indent=2))


def _summary(point: ResumePoint, path: str) -> Dict[str, Any]:
    try:
        size = os.path.getsize(path)
    except OSError:
        size = point.size_bytes()
    return {
        "id": point.id,
        "name": point.name,
        "created_at": point.created_at,
        "digest": point.digest,
        "size_bytes": size,
        "summary": point.describe(),
        "why": point.intent.why,
        "next": point.intent.next_step,
        "stale": point.is_stale(),
        "path": path,
    }


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def save(point: ResumePoint) -> str:
    """Persist a point and update the index. Returns the file path."""
    if not point.digest:
        point.digest = point.to_dict()["digest"]
    path = os.path.join(points_dir(), f"{point.id}.json")
    _atomic_write(path, json.dumps(point.to_dict(), indent=2))

    entries = [entry for entry in _read_index() if entry.get("id") != point.id]
    entries.append(_summary(point, path))
    try:
        _write_index(entries)
    except StoreError:
        # The point itself is written; a broken index only costs a slow lookup.
        pass
    return path


def load(ref: str, allow_path: bool = False) -> ResumePoint:
    """Load by id, by name, by unique name prefix, or (opt-in) by file path.

    ``allow_path`` exists for the CLI's ``--file`` escape hatch. It must stay
    off for anything reachable over HTTP or MCP: a reference from an untrusted
    caller is not a filesystem path.
    """
    if not ref or not str(ref).strip():
        raise PointNotFound(
            "no resume point reference given",
            hint="try `arova list`, or pass a name or id",
        )
    ref = str(ref).strip()

    if allow_path and (os.sep in ref or ref.endswith(".json")):
        if not os.path.exists(ref):
            raise PointNotFound(f"no file at {ref}")
        return _load_file(ref)

    direct = os.path.join(points_dir(), f"{ref}.json")
    if ID_PATTERN.match(ref) and os.path.exists(direct):
        return _load_file(direct)

    if os.path.exists(direct):
        return _load_file(direct)

    entries = _read_index()
    if not entries:
        entries = _rebuild_index()

    exact = [e for e in entries if e.get("name") == ref]
    matches = exact
    if not matches and len(ref) >= MIN_PREFIX:
        matches = [e for e in entries if str(e.get("name", "")).startswith(ref)]

    if not matches:
        raise PointNotFound(
            f"no resume point matching {ref!r}",
            hint="`arova list` shows the names and ids that exist",
        )

    newest = max(matches, key=lambda e: e.get("created_at", 0))
    path = newest.get("path") or os.path.join(points_dir(), f"{newest['id']}.json")
    if not os.path.exists(path):
        _rebuild_index()
        raise PointNotFound(
            f"{ref!r} is indexed but its file is gone ({path})",
            hint="the index has been rebuilt; run `arova list` again",
        )
    return _load_file(path)


def _rebuild_index() -> List[Dict[str, Any]]:
    """Reconstruct the index from the files on disk, skipping damaged files."""
    entries: List[Dict[str, Any]] = []
    for point_id, path in _point_files().items():
        try:
            point = _load_file(path)
        except CorruptPointError:
            continue
        entries.append(_summary(point, path))
    try:
        _write_index(entries)
    except StoreError:
        pass
    return entries


def list_points(include_stale: bool = True, repair: bool = True) -> List[Dict[str, Any]]:
    """All points, newest first. Missing or damaged entries are dropped, not shown."""
    entries = _read_index()
    on_disk = _point_files()

    healthy: List[Dict[str, Any]] = []
    changed = False
    for entry in entries:
        path = entry.get("path") or os.path.join(points_dir(), f"{entry['id']}.json")
        if entry["id"] not in on_disk:
            changed = True
            continue
        if path != on_disk[entry["id"]]:
            entry["path"] = on_disk[entry["id"]]
            changed = True
        # A point on disk is only listed if it actually parses. Listing a
        # damaged point would send the caller to `load`, which would raise.
        try:
            point = _load_file(entry["path"])
        except CorruptPointError:
            changed = True
            continue
        healthy.append(_summary(point, entry["path"]))

    # Files that exist but are not indexed (index lost, or a point copied in).
    indexed = {entry["id"] for entry in healthy}
    for point_id, path in on_disk.items():
        if point_id in indexed:
            continue
        try:
            point = _load_file(path)
        except CorruptPointError:
            changed = True
            continue
        healthy.append(_summary(point, path))
        changed = True

    if changed and repair:
        try:
            _write_index(healthy)
        except StoreError:
            pass

    for entry in healthy:
        entry["age_seconds"] = max(0.0, time.time() - float(entry.get("created_at", 0) or 0))
    healthy.sort(key=lambda e: e.get("created_at", 0), reverse=True)
    if not include_stale:
        healthy = [e for e in healthy if not e.get("stale")]
    return healthy


def latest() -> Optional[Dict[str, Any]]:
    entries = list_points()
    return entries[0] if entries else None


def delete(ref: str) -> bool:
    try:
        point = load(ref)
    except PointNotFound:
        return False
    path = os.path.join(points_dir(), f"{point.id}.json")
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise StoreError(f"cannot delete {path}: {exc}") from exc
    _write_index([e for e in _read_index() if e.get("id") != point.id])
    return True


def gc(max_points: int = 200, max_age_days: float = 30.0) -> int:
    """Delete points beyond ``max_points`` or older than ``max_age_days``."""
    entries = list_points()
    cutoff = time.time() - max_age_days * 86400
    kept: List[Dict[str, Any]] = []
    removed = 0
    for index, entry in enumerate(entries):
        too_old = float(entry.get("created_at", 0) or 0) < cutoff
        too_many = index >= max_points
        if too_old or too_many:
            try:
                os.unlink(entry["path"])
            except OSError:
                pass
            removed += 1
        else:
            kept.append(entry)
    _write_index(kept)
    return removed


def total_size_bytes() -> int:
    return sum(int(entry.get("size_bytes", 0) or 0) for entry in list_points())


def export(point: ResumePoint, path: str) -> str:
    """Write a point somewhere else (e.g. into a repo as a handoff artifact)."""
    _atomic_write(path, json.dumps(point.to_dict(), indent=2))
    return path
