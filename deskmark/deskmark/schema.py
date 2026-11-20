"""The deskmark/v1 data model.

Dataclasses, JSON round-trip, digest. Field names are published in docs/spec.md
and read by other implementations, so renaming one is a format change.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from deskmark import SCHEMA_ID, SCHEMA_VERSION

DEFAULT_TTL_SECONDS = 7 * 24 * 3600


def _now() -> float:
    return time.time()


def _digest(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@dataclass
class Provenance:
    """Where a section came from, and how much to trust it.

    Both the renderer and any agent reading the point look at confidence and
    ttl_seconds, so a provider must not inflate them.
    """

    source: str                 # e.g. "git", "chrome-history", "shell-hook", "proc"
    method: str                 # e.g. "git status --porcelain", "sqlite copy"
    confidence: float = 1.0     # 0..1
    captured_at: float = field(default_factory=_now)
    ttl_seconds: int = DEFAULT_TTL_SECONDS

    def age_seconds(self, now: Optional[float] = None) -> float:
        return (now or _now()) - self.captured_at

    def is_stale(self, now: Optional[float] = None) -> bool:
        return self.age_seconds(now) > self.ttl_seconds

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Provenance":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class RepoState:
    """The git ground truth for the work in flight."""

    root: str
    name: str
    branch: str = ""
    head: str = ""
    remote: str = ""
    ahead: int = 0
    behind: int = 0
    dirty: List[str] = field(default_factory=list)
    staged: List[str] = field(default_factory=list)
    untracked: List[str] = field(default_factory=list)
    recent_commits: List[Dict[str, Any]] = field(default_factory=list)
    diffstat: str = ""

    @property
    def is_clean(self) -> bool:
        return not (self.dirty or self.staged or self.untracked)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RepoState":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class FileRef:
    """A file or folder that belonged to the working set."""

    path: str
    kind: str = "file"          # "file" | "folder"
    reason: str = ""            # "dirty" | "recent" | "terminal-cwd" | "explicit"
    touched_at: float = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TabRef:
    """A page that belonged to the working set."""

    url: str
    title: str = ""
    category: str = "general"   # "development" | "research" | "general"
    host: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TerminalRef:
    """A shell you had rooted somewhere. The command is context, not a script."""

    cwd: str
    shell: str = ""
    last_command: str = ""
    exit_code: Optional[int] = None
    duration_ms: Optional[int] = None
    last_failure: str = ""          # most recent command that exited non-zero
    last_failure_exit: Optional[int] = None
    pid: Optional[int] = None
    at: float = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentRef:
    """An agent that was running when the point was taken.

    resume_hint is the command to pick the session back up. We record it and
    print it; running it is up to you.
    """

    kind: str                   # "claude" | "codex" | "cursor" | "opencode" | ...
    pid: Optional[int] = None
    cwd: str = ""
    session_id: str = ""
    resume_hint: str = ""
    started_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Intent:
    """The part machines cannot infer: why this work exists and what is next."""

    why: str = ""               # best-effort, evidence-derived
    why_source: str = ""        # "commit" | "todo" | "branch" | "note" | "user"
    next_step: str = ""
    next_source: str = ""
    note: str = ""              # anything the human typed at save time
    open_questions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Intent":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class ResumePoint:
    """A portable snapshot of work in flight."""

    name: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=_now)
    ttl_seconds: int = DEFAULT_TTL_SECONDS
    schema: str = SCHEMA_ID
    version: int = SCHEMA_VERSION

    host: Dict[str, str] = field(default_factory=dict)
    repo: Optional[RepoState] = None
    files: List[FileRef] = field(default_factory=list)
    tabs: List[TabRef] = field(default_factory=list)
    terminals: List[TerminalRef] = field(default_factory=list)
    agents: List[AgentRef] = field(default_factory=list)
    intent: Intent = field(default_factory=Intent)

    provenance: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    redactions: List[str] = field(default_factory=list)
    digest: str = ""

    # --- derived ---

    def age_seconds(self, now: Optional[float] = None) -> float:
        return (now or _now()) - self.created_at

    def is_stale(self, now: Optional[float] = None) -> bool:
        return self.age_seconds(now) > self.ttl_seconds

    @property
    def file_count(self) -> int:
        return len(self.files)

    # --- json ---

    def to_dict(self, with_digest: bool = True) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "schema": self.schema,
            "version": self.version,
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "ttl_seconds": self.ttl_seconds,
            "host": dict(self.host),
            "repo": self.repo.to_dict() if self.repo else None,
            "files": [f.to_dict() for f in self.files],
            "tabs": [t.to_dict() for t in self.tabs],
            "terminals": [t.to_dict() for t in self.terminals],
            "agents": [a.to_dict() for a in self.agents],
            "intent": self.intent.to_dict(),
            "provenance": {k: dict(v) for k, v in self.provenance.items()},
            "redactions": list(self.redactions),
        }
        if with_digest:
            data["digest"] = _digest({k: v for k, v in data.items() if k != "digest"})
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResumePoint":
        if not isinstance(data, dict):
            raise ValueError("resume point must be a JSON object")
        schema = data.get("schema", SCHEMA_ID)
        if not str(schema).startswith("deskmark/"):
            raise ValueError(f"unsupported schema: {schema!r}")
        if int(data.get("version", 0)) > SCHEMA_VERSION:
            raise ValueError(
                f"resume point version {data.get('version')} is newer than this build "
                f"(supports {SCHEMA_VERSION}); upgrade deskmark"
            )
        repo = data.get("repo")
        return cls(
            name=data.get("name") or "untitled",
            id=data.get("id") or uuid.uuid4().hex[:12],
            created_at=float(data.get("created_at") or _now()),
            ttl_seconds=int(data.get("ttl_seconds") or DEFAULT_TTL_SECONDS),
            schema=schema,
            version=int(data.get("version") or SCHEMA_VERSION),
            host=dict(data.get("host") or {}),
            repo=RepoState.from_dict(repo) if repo else None,
            files=[FileRef(**f) for f in data.get("files") or []],
            tabs=[TabRef(**t) for t in data.get("tabs") or []],
            terminals=[TerminalRef(**t) for t in data.get("terminals") or []],
            agents=[AgentRef(**a) for a in data.get("agents") or []],
            intent=Intent.from_dict(data.get("intent") or {}),
            provenance=dict(data.get("provenance") or {}),
            redactions=list(data.get("redactions") or []),
            digest=data.get("digest", ""),
        )

    def verify(self) -> bool:
        """True when the stored digest matches the contents."""
        if not self.digest:
            return False
        return self.to_dict(with_digest=True)["digest"] == self.digest

    def size_bytes(self) -> int:
        return len(json.dumps(self.to_dict(), indent=2).encode("utf-8"))

    def describe(self) -> str:
        """One-line summary used by the CLI and by agents."""
        bits = []
        if self.repo:
            state = "clean" if self.repo.is_clean else f"{len(self.repo.dirty) + len(self.repo.untracked)} changed"
            bits.append(f"{self.repo.name}@{self.repo.branch or '?'} ({state})")
        if self.tabs:
            bits.append(f"{len(self.tabs)} tab" + ("" if len(self.tabs) == 1 else "s"))
        if self.terminals:
            bits.append(f"{len(self.terminals)} shell" + ("" if len(self.terminals) == 1 else "s"))
        if self.agents:
            bits.append("agents: " + ",".join(sorted({a.kind for a in self.agents})))
        if not bits:
            return "empty resume point"
        return " · ".join(bits)


def local_host_info() -> Dict[str, str]:
    """Identify the machine so a restore can warn about a different context."""
    return {
        "hostname": socket.gethostname(),
        "os": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "user": os.environ.get("USER") or os.environ.get("USERNAME") or "",
    }
