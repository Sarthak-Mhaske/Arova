"""Browser history, read straight out of the sqlite files.

Browsers keep the database locked while they run, so we copy it to a temp file,
read the copy and delete it. No extension, no permissions, no sync.

Filtering happens before anything is written; the policy lives in privacy.py.
"""
from __future__ import annotations

import glob
import os
import shutil
import sqlite3
import tempfile
import time
from typing import List, Optional, Tuple

from deskmark.providers.privacy import (
    Verdict,
    categorize,
    classify,
    clean_url,
    redaction_summary,
)
from deskmark.schema import TabRef

CHROME_CHAINS = (
    ("google-chrome", "Google/Chrome"),
    ("chromium", "Chromium"),
    ("brave-browser", "BraveSoftware/Brave-Browser"),
    ("microsoft-edge", "Microsoft/Edge"),
    ("vivaldi", "Vivaldi"),
    ("arc", "Arc/User Data"),
)

# chrome counts microseconds from 1601, firefox counts seconds from 1970
CHROME_EPOCH_OFFSET_US = 11644473600 * 1_000_000


def candidate_databases() -> List[Tuple[str, str]]:
    """Return (path, engine) for every browser profile we can find."""
    home = os.path.expanduser("~")
    found: List[Tuple[str, str]] = []

    if os.path.isdir("/proc") or os.name != "nt":  # linux & macOS layout
        for dirname, _ in CHROME_CHAINS:
            for root in (
                os.path.join(home, ".config", dirname),
                os.path.join(home, "Library", "Application Support", *(dirname.split("/"))),
            ):
                found.extend((path, "chromium") for path in _chrome_history_files(root))
        for pattern in (
            os.path.join(home, ".mozilla", "firefox", "*", "places.sqlite"),
            os.path.join(home, "Library", "Application Support", "Firefox", "Profiles", "*", "places.sqlite"),
        ):
            found.extend((path, "firefox") for path in glob.glob(pattern))

    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        roaming = os.environ.get("APPDATA", "")
        if local:
            for _, chain in CHROME_CHAINS:
                root = os.path.join(local, *chain.split("/"))
                if os.path.isdir(os.path.join(root, "User Data")):
                    root = os.path.join(root, "User Data")
                found.extend((p, "chromium") for p in _chrome_history_files(root))
        if roaming:
            pattern = os.path.join(roaming, "Mozilla", "Firefox", "Profiles", "*", "places.sqlite")
            found.extend((p, "firefox") for p in glob.glob(pattern))

    return found


def _chrome_history_files(root: str) -> List[str]:
    if not os.path.isdir(root):
        return []
    paths = [os.path.join(root, "Default", "History")]
    paths.extend(sorted(glob.glob(os.path.join(root, "Profile *", "History"))))
    return [p for p in paths if os.path.exists(p)]


def _query(path: str, engine: str, since: float, limit: int) -> List[Tuple[str, str, float]]:
    rows: List[Tuple[str, str, float]] = []
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        # only the main db file is copied, not -wal, so anything the browser
        # hasn't checkpointed yet (usually the last few minutes) is missing here.
        shutil.copy2(path, tmp)
        connection = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True, timeout=2.0)
        try:
            cursor = connection.cursor()
            if engine == "firefox":
                cursor.execute(
                    "SELECT url, title, last_visit_date FROM moz_places "
                    "WHERE last_visit_date > ? AND url LIKE 'http%' AND title IS NOT NULL "
                    "ORDER BY last_visit_date DESC LIMIT ?",
                    (int(since * 1_000_000), limit * 4),
                )
                for url, title, stamp in cursor.fetchall():
                    rows.append((url, title or url, float(stamp or 0) / 1_000_000))
            else:
                cursor.execute(
                    "SELECT url, title, last_visit_time FROM urls "
                    "WHERE last_visit_time > ? AND url LIKE 'http%' AND title IS NOT NULL "
                    "ORDER BY last_visit_time DESC LIMIT ?",
                    (int((since * 1_000_000) + CHROME_EPOCH_OFFSET_US), limit * 4),
                )
                for url, title, stamp in cursor.fetchall():
                    rows.append((url, title or url, (float(stamp or 0) - CHROME_EPOCH_OFFSET_US) / 1_000_000))
        finally:
            connection.close()
    except Exception:
        return []
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return rows


def read_recent(limit: int = 12, max_age_hours: float = 12.0) -> Tuple[Optional[List[TabRef]], List[str], int]:
    """Return (tabs, redaction_summary, profiles_seen). ``None`` = no browser found."""
    databases = candidate_databases()
    if not databases:
        return None, [], 0

    since = time.time() - max_age_hours * 3600
    raw: List[Tuple[str, str, float]] = []
    for path, engine in databases:
        raw.extend(_query(path, engine, since, limit))

    if not raw:
        return [], [], len(databases)

    raw.sort(key=lambda row: row[2], reverse=True)

    dropped: List[str] = []
    kept: List[TabRef] = []
    seen_urls = set()
    seen_titles = set()

    for url, title, _stamp in raw:
        cleaned, clean_title = clean_url(url, title)
        decision = classify(cleaned, clean_title)
        if decision.verdict is Verdict.DROP:
            dropped.append(decision.reason)
            continue
        if cleaned in seen_urls:
            continue
        title_key = clean_title.lower()
        if title_key and title_key in seen_titles:
            continue
        seen_urls.add(cleaned)
        seen_titles.add(title_key)
        try:
            from urllib.parse import urlparse
            host = (urlparse(cleaned).hostname or "").lower()
        except Exception:
            host = ""
        kept.append(TabRef(url=cleaned, title=clean_title[:200] or cleaned,
                           category=categorize(cleaned, clean_title), host=host))

    # work pages first: resuming into docs beats resuming into news
    priority = {"development": 0, "research": 1, "general": 2}
    kept.sort(key=lambda tab: priority.get(tab.category, 3))
    return kept[:limit], redaction_summary(dropped), len(databases)
