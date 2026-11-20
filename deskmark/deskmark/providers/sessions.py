"""Open tabs, read out of the file the browser restores from.

History was the wrong source and the bug was visible: chrome keeps a row for
every url you touched in the last 90 days, so "newest 12 rows" is a summary of
your afternoon, not a list of open tabs. Session logs answer the actual
question, because closing a tab appends a close marker to them.

Chrome names its session in a way worth knowing before touching this file:

    Sessions/Session_<ts>   the current run. this is the one we read
    Sessions/Tabs_<ts>      recently *closed* tabs. deliberately not read

so a tab that appears in Session_ without a close marker afterwards is open,
and one that was closed is not. Firefox's sessionstore-backups/recovery.jsonlz4
is the same idea in a different format, rewritten in place every few seconds.

Both parsers are read-only and both fail closed: anything malformed, truncated
or half-written returns no tabs rather than a guess. Nothing here is written
back, and no browser file is ever modified or locked.
"""
from __future__ import annotations

import glob
import json
import os
import struct
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Set, Tuple

from deskmark.providers.privacy import (
    Verdict,
    categorize,
    classify,
    clean_url,
    redaction_summary,
)
from deskmark.schema import TabRef

# a session log is a few hundred KB; this is a guard against a pathological file
MAX_SESSION_BYTES = 32 * 1024 * 1024

# chromium profiles older than these aren't worth a second look
MAX_PROFILES = 8

# command ids, components/sessions/core/session_service_commands.cc
CMD_SET_TAB_WINDOW = 0
CMD_SET_TAB_INDEX = 2
CMD_TAB_NAVIGATION = 6
CMD_SELECTED_NAVIGATION = 7
CMD_SELECTED_TAB = 8
CMD_TAB_CLOSED = 16
CMD_WINDOW_CLOSED = 17
CMD_ACTIVE_WINDOW = 20

# where each browser keeps its profiles: linux config dir, macOS app support dir,
# windows app support dir, and the same thing under a flatpak sandbox.
# flatpak keeps its own layout, so brave is BraveSoftware/Brave-Browser in all
# three while chrome is google-chrome natively and in the sandbox.
CHROME_CHAINS = (
    # linux                  macOS                    windows                    flatpak app id          path in sandbox
    ("google-chrome", "Google/Chrome", "Google/Chrome", "com.google.Chrome", "google-chrome", "chrome"),
    ("chromium", "Chromium", "Chromium", "org.chromium.Chromium", "chromium", "chromium"),
    ("brave-browser", "BraveSoftware/Brave-Browser", "BraveSoftware/Brave-Browser",
     "com.brave.Browser", "BraveSoftware/Brave-Browser", "brave"),
    ("microsoft-edge", "Microsoft Edge", "Microsoft/Edge", "com.microsoft.Edge",
     "microsoft-edge", "edge"),
    ("vivaldi", "Vivaldi", "Vivaldi", "com.vivaldi.Vivaldi", "vivaldi", "vivaldi"),
    ("arc", "Arc/User Data", "TheBrowserCompany.Arc/LocalCache/Local/Arc/User Data",
     None, "", "arc"),
)

MOZ_MAGIC = b"mozLz40\0"

# firefox writes several of these and they are not equivalent: recovery is the
# live session, sessionstore.jsonlz4 only exists after a clean shutdown
FIREFOX_SESSION_FILES = (
    ("sessionstore-backups", "recovery.jsonlz4"),
    ("sessionstore-backups", "recovery.baklz4"),
    ("", "sessionstore.jsonlz4"),
    ("sessionstore-backups", "previous.jsonlz4"),
)


@dataclass
class _Tab:
    tab_id: int
    window: Optional[int] = None
    index: int = 0
    closed: bool = False
    selected: Optional[int] = None
    # navigation index -> (url, title); the index is the tab's own history slot
    navs: Dict[int, Tuple[str, str]] = field(default_factory=dict)

    def current(self) -> Optional[Tuple[str, str]]:
        if not self.navs:
            return None
        if self.selected is not None and self.selected in self.navs:
            return self.navs[self.selected]
        return self.navs[max(self.navs)]


class _Reader:
    """Just enough of base::Pickle to walk a command payload."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def u32(self) -> int:
        if self.pos + 4 > len(self.data):
            raise ValueError("short u32")
        value = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return value

    def string(self) -> str:
        size = self.u32()
        if size > len(self.data) - self.pos:
            raise ValueError("short string")
        raw = self.data[self.pos:self.pos + size]
        # pickles pad every field to a 4 byte boundary. miss this and the title
        # is read out of the middle of the url.
        self.pos += size + (-size % 4)
        return raw.decode("utf-8", "replace")

    def string16(self) -> str:
        chars = self.u32()
        size = chars * 2
        if size > len(self.data) - self.pos:
            raise ValueError("short string16")
        raw = self.data[self.pos:self.pos + size]
        self.pos += size + (-size % 4)
        return raw.decode("utf-16-le", "replace")


def _payload(body: bytes) -> bytes:
    """Strip the leading length that base::Pickle::data() puts in front.

    Some commands are pickled and some are a straight memory dump of a small
    struct, so the header is only there sometimes. The size means itself: if
    the first word equals the rest of the payload, it's a header.
    """
    if len(body) >= 4 and struct.unpack_from("<I", body, 0)[0] == len(body) - 4:
        return body[4:]
    return body


def _navigation(body: bytes) -> Optional[Tuple[int, int, str, str]]:
    """(tab_id, history index, url, title) from an update-navigation payload."""
    for candidate in (_payload(body), body):
        try:
            reader = _Reader(candidate)
            tab_id = reader.u32()
            index = reader.u32()
            url = reader.string()
            title = reader.string16()
        except ValueError:
            continue
        if _is_web(url):
            return tab_id, index, url, title
    return None


def _id_and_value(body: bytes) -> Optional[Tuple[int, int]]:
    try:
        reader = _Reader(_payload(body))
        return reader.u32(), reader.u32()
    except ValueError:
        return None


def _one_id(body: bytes) -> Optional[int]:
    try:
        return _Reader(_payload(body)).u32()
    except ValueError:
        return None


def _is_web(url: str) -> bool:
    lowered = url.lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _commands(data: bytes) -> Iterator[Tuple[int, bytes]]:
    """Walk the SNSS record stream. Stops quietly on a truncated tail."""
    if len(data) < 8 or data[:4] != b"SNSS":
        return
    version = struct.unpack_from("<I", data, 4)[0]
    if version not in (1, 2, 3):
        return
    pos = 8
    while pos + 2 <= len(data):
        size = struct.unpack_from("<H", data, pos)[0]
        if size < 2:                      # zero length record, nothing sane follows
            return
        body = data[pos + 2:pos + 2 + size]
        if len(body) < size:              # browser is mid-write, stop at the tear
            return
        yield body[0], body[1:]
        pos += 2 + size


def parse_chrome_session(data: bytes) -> List[Tuple[str, str]]:
    """Open (url, title) pairs from one Session_* file, in tab order."""
    tabs: Dict[int, _Tab] = {}
    closed_windows: Set[int] = set()
    active_window: Optional[int] = None

    for command, body in _commands(data):
        if command == CMD_TAB_NAVIGATION:
            navigation = _navigation(body)
            if navigation is None:
                continue
            tab_id, index, url, title = navigation
            tabs.setdefault(tab_id, _Tab(tab_id)).navs[index] = (url, title)
        elif command == CMD_SET_TAB_WINDOW:
            pair = _id_and_value(body)
            if pair:
                window_id, tab_id = pair
                tabs.setdefault(tab_id, _Tab(tab_id)).window = window_id
        elif command == CMD_SET_TAB_INDEX:
            pair = _id_and_value(body)
            if pair:
                tab_id, index = pair
                tabs.setdefault(tab_id, _Tab(tab_id)).index = index
        elif command == CMD_SELECTED_NAVIGATION:
            pair = _id_and_value(body)
            if pair:
                tab_id, index = pair
                tabs.setdefault(tab_id, _Tab(tab_id)).selected = index
        elif command == CMD_TAB_CLOSED:
            tab_id = _one_id(body)
            if tab_id is not None:
                tabs.setdefault(tab_id, _Tab(tab_id)).closed = True
        elif command == CMD_WINDOW_CLOSED:
            window_id = _one_id(body)
            if window_id is not None:
                closed_windows.add(window_id)
        elif command == CMD_ACTIVE_WINDOW:
            active_window = _one_id(body)

    open_tabs = [
        tab for tab in tabs.values()
        if not tab.closed and tab.window not in closed_windows and tab.current()
    ]
    # the window you were looking at comes first, then browser tab order
    open_tabs.sort(key=lambda tab: (tab.window != active_window, tab.window or 0, tab.index))
    return [tab.current() for tab in open_tabs]  # type: ignore[misc]


def _read_bytes(path: str) -> Optional[bytes]:
    try:
        if os.path.getsize(path) > MAX_SESSION_BYTES:
            return None
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


def _profile_dirs(root: str) -> List[str]:
    if not os.path.isdir(root):
        return []
    found = [os.path.join(root, "Default")]
    found.extend(sorted(glob.glob(os.path.join(root, "Profile *"))))
    return [path for path in found if os.path.isdir(path)][:MAX_PROFILES]


def chrome_profile_dirs() -> List[Tuple[str, str]]:
    """(profile dir, brand) for every chromium-family profile we can find."""
    home = os.path.expanduser("~")
    found: List[Tuple[str, str]] = []
    for linux_name, mac_name, windows_name, flatpak_id, flatpak_path, brand in CHROME_CHAINS:
        if os.name == "nt":
            local = os.environ.get("LOCALAPPDATA", "")
            roots = [os.path.join(local, *windows_name.split("/"))] if local else []
        else:
            roots = [
                os.path.join(home, ".config", linux_name),
                os.path.join(home, "Library", "Application Support", *mac_name.split("/")),
            ]
            if flatpak_id and flatpak_path:
                roots.append(os.path.join(home, ".var", "app", flatpak_id, "config",
                                          *flatpak_path.split("/")))
        for root in roots:
            found.extend((path, brand) for path in _profile_dirs(root))
    return found


def firefox_profile_dirs() -> List[Tuple[str, str]]:
    home = os.path.expanduser("~")
    patterns = [
        os.path.join(home, ".mozilla", "firefox", "*"),
        os.path.join(home, ".var", "app", "org.mozilla.firefox", ".mozilla", "firefox", "*"),
        os.path.join(home, "Library", "Application Support", "Firefox", "Profiles", "*"),
    ]
    if os.name == "nt":
        roaming = os.environ.get("APPDATA", "")
        if roaming:
            patterns.append(os.path.join(roaming, "Mozilla", "Firefox", "Profiles", "*"))
    found: List[Tuple[str, str]] = []
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            if os.path.isfile(os.path.join(path, "places.sqlite")):
                found.append((path, "firefox"))
    return found[:MAX_PROFILES]


def _stamp(path: str) -> Tuple[int, float]:
    """Rank session files by the number chrome put in the name.

    Not mtime: a profile that gets copied or restored from a backup keeps the
    filename but loses the timestamp, and then the older session looks newer.
    """
    name = os.path.basename(path)
    tail = name.rsplit("_", 1)[-1]
    try:
        return int(tail), os.path.getmtime(path)
    except (ValueError, OSError):
        return 0, os.path.getmtime(path) if os.path.exists(path) else 0.0


def chrome_session_file(profile: str) -> Optional[str]:
    """The log for the run that is live, or the one that just ended.

    Only Session_*. The sibling Tabs_* file is the *recently closed* list, which
    is the opposite of what a resume point is for.
    """
    sessions = [path for path in glob.glob(os.path.join(profile, "Sessions", "Session_*"))
                if os.path.isfile(path)]
    if sessions:
        return max(sessions, key=_stamp)
    for name in ("Current Session", "Last Session"):   # chrome before Sessions/ existed
        path = os.path.join(profile, name)
        if os.path.isfile(path):
            return path
    return None


def read_chrome_tabs(profile: str) -> List[Tuple[str, str]]:
    path = chrome_session_file(profile)
    if not path:
        return []
    data = _read_bytes(path)
    if not data:
        return []
    try:
        return parse_chrome_session(data)
    except Exception:          # a format we don't know is not a reason to fail capture
        return []


def lz4_block(data: bytes, expected: Optional[int] = None) -> bytes:
    """Decompress a raw LZ4 block. mozilla's jsonlz4 is a header plus this."""
    out = bytearray()
    pos = 0
    size = len(data)
    while pos < size:
        token = data[pos]
        pos += 1

        literals = token >> 4
        if literals == 15:
            while pos < size:
                extra = data[pos]
                pos += 1
                literals += extra
                if extra != 255:
                    break
        if pos + literals > size:
            raise ValueError("truncated literals")
        out += data[pos:pos + literals]
        pos += literals

        if pos >= size:                # last sequence carries no match
            break
        if pos + 2 > size:
            raise ValueError("truncated offset")

        offset = data[pos] | (data[pos + 1] << 8)
        pos += 2
        if offset == 0 or offset > len(out):
            raise ValueError("offset outside the window")

        length = token & 0x0F
        if length == 15:
            while pos < size:
                extra = data[pos]
                pos += 1
                length += extra
                if extra != 255:
                    break
        length += 4

        start = len(out) - offset
        for step in range(length):     # byte at a time: the copy may overlap
            out.append(out[start + step])

    if expected is not None and len(out) != expected:
        raise ValueError(f"expected {expected} bytes, decoded {len(out)}")
    return bytes(out)


def mozlz4(data: bytes) -> bytes:
    if len(data) < 12 or data[:8] != MOZ_MAGIC:
        raise ValueError("not mozlz4")
    expected = struct.unpack_from("<I", data, 8)[0]
    return lz4_block(data[12:], expected)


def parse_firefox_session(payload: dict) -> List[Tuple[str, str]]:
    """Open (url, title) pairs from a decoded sessionstore document."""
    tabs: List[Tuple[str, str]] = []
    for window in payload.get("windows") or []:
        for tab in window.get("tabs") or []:
            entries = tab.get("entries") or []
            if not entries:
                continue
            index = tab.get("index") or len(entries)
            entry = entries[index - 1] if 0 < index <= len(entries) else entries[-1]
            url = entry.get("url") or ""
            title = entry.get("title") or url
            if _is_web(url):
                tabs.append((url, title))
    return tabs


def read_firefox_tabs(profile: str) -> List[Tuple[str, str]]:
    for folder, name in FIREFOX_SESSION_FILES:
        path = os.path.join(profile, folder, name) if folder else os.path.join(profile, name)
        if not os.path.isfile(path):
            continue
        data = _read_bytes(path)
        if not data:
            continue
        try:
            document = json.loads(mozlz4(data).decode("utf-8", "replace"))
        except Exception:
            continue
        if isinstance(document, dict):
            tabs = parse_firefox_session(document)
            if tabs:
                return tabs
    return []


def _admit(raw: List[Tuple[str, str]], limit: int) -> Tuple[List[TabRef], List[str]]:
    """Filter to pages that may be recorded, then order work first."""
    dropped: List[str] = []
    kept: List[TabRef] = []
    seen_urls: Set[str] = set()
    seen_titles: Set[str] = set()

    for url, title in raw:
        cleaned, clean_title = clean_url(url, title)
        decision = classify(cleaned, clean_title)
        if decision.verdict is Verdict.DROP:
            dropped.append(decision.reason)
            continue
        if not clean_title.strip():
            clean_title = cleaned
        if cleaned in seen_urls or clean_title.lower() in seen_titles:
            continue
        seen_urls.add(cleaned)
        seen_titles.add(clean_title.lower())
        host = (cleaned.split("/")[2].split(":")[0] if "//" in cleaned else "").lower()
        kept.append(TabRef(url=cleaned, title=clean_title[:200],
                           category=categorize(cleaned, clean_title), host=host))

    priority = {"development": 0, "research": 1, "general": 2}
    kept.sort(key=lambda tab: priority.get(tab.category, 3))
    return kept[:limit], redaction_summary(dropped)


def open_tabs(limit: int = 12) -> Tuple[Optional[List[TabRef]], List[str], int]:
    """Return (tabs, redaction summary, profiles seen). ``None`` = no browser.

    An empty list means every profile was read and nothing is open, which is
    what a closed browser looks like. That stays empty on purpose: reopening a
    page from six hours ago because it happens to be in history is exactly the
    behaviour this module exists to remove.
    """
    chrome = chrome_profile_dirs()
    firefox = firefox_profile_dirs()
    profiles = chrome + firefox
    if not profiles:
        return None, [], 0

    raw: List[Tuple[str, str]] = []
    for profile, brand in profiles:
        try:
            raw.extend(read_firefox_tabs(profile) if brand == "firefox" else read_chrome_tabs(profile))
        except Exception:      # one unreadable profile must not sink the others
            continue

    tabs, redactions = _admit(raw, limit)
    return tabs, redactions, len(profiles)
