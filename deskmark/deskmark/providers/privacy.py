"""What is allowed into a resume point.

Decisions use the host and path only, never the page title: a filter that
matched text would quietly delete real work. Anything dropped is counted and
stored as a category, so the point says something was withheld without saying
what.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple


class Verdict(str, Enum):
    KEEP = "keep"
    DROP = "drop"


# Blocked hosts, grouped by the reason that gets written into the point.
# Matching is on the registrable domain or a subdomain of it; a rule may also
# carry a path prefix, like "stripe.com/dashboard".
#
# The group name goes into the point, the host does not. Writing "chase.com" in
# the summary would leak the thing the drop was for.
BLOCKED_DOMAINS: Dict[str, Tuple[str, ...]] = {
    "banking": (
        "chase.com", "wellsfargo.com", "bankofamerica.com", "citibank.com", "hsbc.com",
        "icicibank.com", "hdfcbank.com", "sbi.co.in", "axisbank.com", "kotak.com",
        "paypal.com", "stripe.com/dashboard", "checkout.stripe.com", "razorpay.com",
        "adyen.com", "wise.com",
    ),
    "trading": (
        "zerodha.com", "groww.in", "upstox.com", "coinbase.com", "binance.com",
        "kite.zerodha.com", "interactivebrokers.com", "schwab.com", "fidelity.com",
    ),
    "identity": (
        "accounts.google.com", "login.microsoftonline.com", "login.live.com",
        "appleid.apple.com", "okta.com", "auth0.com", "onelogin.com", "duo.com",
        "lastpass.com", "1password.com", "bitwarden.com", "dashlane.com",
        "keepersecurity.com", "nordpass.com", "proton.me/pass",
    ),
    "tax-and-government": (
        "incometax.gov.in", "irs.gov", "passportindia.gov.in", "gov.uk",
        "uidai.gov.in", "mychart.com",
    ),
    "health": (
        "practo.com", "1mg.com", "pharmeasy.in", "apollopharmacy.in", "netmeds.com",
        "cvs.com", "walgreens.com",
    ),
    "webmail": (
        "mail.google.com", "outlook.live.com", "outlook.office.com", "mail.yahoo.com",
        "protonmail.com", "mail.proton.me", "fastmail.com", "zoho.com/mail",
    ),
    "calendar": (
        "calendar.google.com", "calendly.com", "cal.com",
    ),
    "social": (
        "instagram.com", "tiktok.com", "facebook.com", "x.com", "twitter.com",
        "pinterest.com", "web.whatsapp.com", "messenger.com", "chat.google.com",
        "discord.com", "reddit.com/chat",
    ),
}

# Path/query fragments that indicate a sensitive session regardless of host.
BLOCKED_FRAGMENTS: Tuple[str, ...] = (
    "/password", "/reset", "/2fa", "/two-factor", "/oauth", "/signin", "/login",
    "/servicelogin", "/checkout/session", "/billing/portal", "session_token=",
    "access_token=", "id_token=", "code=", "/captcha", "/sorry/",
)

# Host labels that are sensitive by convention, wherever they appear.
SENSITIVE_LABELS: Tuple[str, ...] = (
    "bank", "banking", "wallet", "brokerage", "invest", "payments", "netbanking",
    "health", "medical", "clinic", "hospital", "patient", "pharmacy", "insurance",
    "vault", "keychain", "keyring",
)

# Local development bridges: our own UI, never useful to restore.
LOCAL_NOISE_PORTS = ("8765", "5173", "1420", "3030")

BORING_TITLES = ("new tab", "home", "untitled", "about:blank", "loading...",
                 "page not found", "404 not found", "access denied", "bad gateway")


@dataclass
class Decision:
    verdict: Verdict
    reason: str = ""

    @property
    def keep(self) -> bool:
        return self.verdict is Verdict.KEEP


def _domain_matches(host: str, rule: str) -> bool:
    if "/" in rule:                     # rule includes a path prefix
        return False
    return host == rule or host.endswith("." + rule)


def classify(url: str, title: str = "") -> Decision:
    """Decide whether a page may be recorded. Host and path only."""
    if not url:
        return Decision(Verdict.DROP, "empty url")

    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return Decision(Verdict.DROP, "unparseable url")

    if parsed.scheme not in ("http", "https"):
        return Decision(Verdict.DROP, f"scheme {parsed.scheme or '?'}")

    host = (parsed.hostname or "").lower()
    path = (parsed.path or "/").lower()
    query = (parsed.query or "").lower()

    if not host:
        return Decision(Verdict.DROP, "no host")

    local = host in ("localhost", "127.0.0.1", "::1", "0.0.0.0")
    if local and any(f":{port}" in url for port in LOCAL_NOISE_PORTS):
        return Decision(Verdict.DROP, "withheld: local dev server")

    for category, rules in BLOCKED_DOMAINS.items():
        for rule in rules:
            if "/" in rule:
                rule_host, rule_path = rule.split("/", 1)
                if _domain_matches(host, rule_host) and path.startswith("/" + rule_path):
                    return Decision(Verdict.DROP, f"withheld: {category}")
            elif _domain_matches(host, rule):
                return Decision(Verdict.DROP, f"withheld: {category}")

    # match inside the label, not just as a whole one: my.healthprovider.com has
    # no label called "health" and is exactly the host this rule is for. it
    # over-drops (investopedia.com goes too), which is the side to be wrong on.
    host_labels = host.split(".")
    for label in SENSITIVE_LABELS:
        if any(label in part for part in host_labels):
            return Decision(Verdict.DROP, "withheld: sensitive host name")

    haystack = path + "?" + query
    for fragment in BLOCKED_FRAGMENTS:
        if fragment in haystack:
            return Decision(Verdict.DROP, f"withheld: auth or payment path ({fragment.strip('/')})")

    # /admin on a remote host is somebody else's console. On localhost it's your
    # dev server, which is the thing restore exists for.
    if not local and (path.startswith("/admin") or path.startswith("/wp-admin")
                      or path.startswith("/manage")):
        return Decision(Verdict.DROP, "withheld: admin console")

    lowered_title = (title or "").strip().lower()
    if lowered_title in BORING_TITLES:
        return Decision(Verdict.DROP, "blank page")

    return Decision(Verdict.KEEP)


def clean_url(url: str, title: str = "") -> Tuple[str, str]:
    """Strip tracking noise and badge counters without changing the target."""
    clean_title = re.sub(r"^\s*[\(\[]\d+[\)\]]\s*", "", title or "").strip()
    for suffix in (" - Google Chrome", " - Brave", " - Mozilla Firefox",
                   " - Microsoft Edge", " - Chromium", " - Arc", " - Vivaldi"):
        if clean_title.endswith(suffix):
            clean_title = clean_title[: -len(suffix)].strip()

    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return url, clean_title

    drop_params = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "ref_src", "spm",
        "si", "s", "t", "_ga", "igshid", "share_id",
    }
    kept = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
            if k.lower() not in drop_params]
    query = urllib.parse.urlencode(kept, doseq=True)
    cleaned = urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/") or "/",
         parsed.params, query, "")
    )
    return cleaned, clean_title


def categorize(url: str, title: str = "") -> str:
    text = f"{url} {title}".lower()
    if any(key in text for key in ("github.com", "gitlab.com", "linear.app", "jira",
                                   "notion.so", "confluence", "stackoverflow.com",
                                   "localhost", "127.0.0.1", "vercel.com", "sentry.io")):
        return "development"
    if any(key in text for key in ("docs", "documentation", "arxiv", "paper", "rfc",
                                   "wikipedia", "medium.com", "dev.to", "blog",
                                   "tutorial", "spec")):
        return "research"
    return "general"


REDACTED = "[redacted]"

# Order matters: the keyword rule runs first so "--password=sk-live-123" comes
# out as "--password=[redacted]" rather than half redacted. Every rule keys off
# a shape, not off a word turning up somewhere in a sentence.
_SECRET_RULES = (
    # key = value, key: value, --key=value, "key": "value"
    (re.compile(
        r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|apikey|auth[_-]?key"
        r"|access[_-]?key|private[_-]?key|client[_-]?secret|credentials?)\b"
        r"(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)"), r"\1\2" + REDACTED),
    # long flags with a space: --password hunter2, --token abc.
    # short flags are not inferred: -p is a port, a print or a password
    # depending on the program, and guessing deletes real context.
    (re.compile(
        r"(?i)(--(?:password|passwd|token|api-key|apikey|secret|auth-token"
        r"|access-token|client-secret)\s+)(\S+)"), r"\1" + REDACTED),
    # Authorization: Bearer <token>
    (re.compile(r"(?i)(\bbearer\s+)([A-Za-z0-9._\-]{6,})"), r"\1" + REDACTED),
    # scheme://user:pass@host -- no keyword in it for the rules above to catch
    (re.compile(r"(\b[a-z][a-z0-9+.\-]*://[^/\s:@]+):([^/\s@]+)@"), r"\1:" + REDACTED + "@"),
    # well-known token shapes, with no keyword in front of them
    (re.compile(
        r"\b(sk-[A-Za-z0-9_\-]{8,}|ghp_[A-Za-z0-9]{8,}|gho_[A-Za-z0-9]{8,}"
        r"|github_pat_[A-Za-z0-9_]{8,}|glpat-[A-Za-z0-9_\-]{8,}|npm_[A-Za-z0-9]{8,}"
        r"|xox[baprs]-[A-Za-z0-9\-]{6,}|AIza[0-9A-Za-z_\-]{10,}"
        r"|AKIA[0-9A-Z]{12,}|ASIA[0-9A-Z]{12,})"), REDACTED),
)


def redact_command(command: str) -> Tuple[str, int]:
    """Return (safe text, number of redactions).

    The command is kept and the credential cut out. Dropping the whole line
    would hide the work along with the secret, and the last failing command is
    the most useful thing in a point.
    """
    text = command or ""
    total = 0
    for pattern, replacement in _SECRET_RULES:
        text, count = pattern.subn(replacement, text)
        total += count
    return text, total


def redaction_summary(dropped: List[str]) -> List[str]:
    """Aggregate drop reasons, without repeating URLs."""
    counts: dict = {}
    for reason in dropped:
        counts[reason] = counts.get(reason, 0) + 1
    return [f"{reason} ×{count}" for reason, count in sorted(counts.items())]
