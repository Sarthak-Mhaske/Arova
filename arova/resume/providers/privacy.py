"""What is allowed into a resume point.

This is the most important file in the product, so it is explicit rather than
clever:

* Decide on the **host and path**, never on free-text titles. A filter that
  matches the word "checkout" inside a pull request title silently deletes real
  work, and silent deletion is worse than no capture at all.
* Two outcomes only: **keep** or **drop**. Anything dropped is counted, and the
  count is written into the resume point, so the human can see that something
  was withheld instead of assuming the tool saw everything.
* Being wrong in the direction of dropping is acceptable for credentials,
  payments, health and identity. Being wrong in the direction of keeping is not.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


class Verdict(str, Enum):
    KEEP = "keep"
    DROP = "drop"


# Hosts that must never appear in a resume point, matched against the exact
# registrable domain or one of its subdomains.
BLOCKED_DOMAINS: Tuple[str, ...] = (
    # banking & payments
    "chase.com", "wellsfargo.com", "bankofamerica.com", "citibank.com", "hsbc.com",
    "icicibank.com", "hdfcbank.com", "sbi.co.in", "axisbank.com", "kotak.com",
    "paypal.com", "stripe.com/dashboard", "razorpay.com", "checkout.stripe.com",
    "zerodha.com", "groww.in", "upstox.com", "coinbase.com", "binance.com",
    # identity & auth
    "accounts.google.com", "login.microsoftonline.com", "login.live.com",
    "appleid.apple.com", "okta.com", "auth0.com", "onelogin.com", "duo.com",
    # health, tax, government
    "incometax.gov.in", "irs.gov", "aadhaar", "passportindia.gov.in",
    "mychart.com", "practo.com", "1mg.com",
    # webmail: high volume, low resumption value
    "mail.google.com", "outlook.live.com", "outlook.office.com", "mail.yahoo.com",
    # social & chat: ephemeral, and other people's words
    "instagram.com", "tiktok.com", "facebook.com", "x.com", "twitter.com",
    "pinterest.com", "web.whatsapp.com", "messenger.com", "chat.google.com",
    "discord.com",
)

# Path/query fragments that indicate a sensitive session regardless of host.
BLOCKED_FRAGMENTS: Tuple[str, ...] = (
    "/password", "/reset", "/2fa", "/two-factor", "/oauth", "/signin", "/login",
    "/servicelogin", "/checkout/session", "/billing/portal", "session_token=",
    "access_token=", "id_token=", "code=", "/captcha", "/sorry/",
)

# Host labels that are sensitive by convention, wherever they appear.
SENSITIVE_LABELS: Tuple[str, ...] = ("bank", "banking", "wallet", "brokerage",
                                     "invest", "payments", "netbanking")

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

    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        if any(f":{port}" in url for port in LOCAL_NOISE_PORTS):
            return Decision(Verdict.DROP, "local arova/dev ui")
        return Decision(Verdict.KEEP)

    for rule in BLOCKED_DOMAINS:
        if "/" in rule:
            rule_host, rule_path = rule.split("/", 1)
            if _domain_matches(host, rule_host) and path.startswith("/" + rule_path):
                return Decision(Verdict.DROP, f"sensitive host {rule}")
        elif _domain_matches(host, rule):
            return Decision(Verdict.DROP, f"sensitive host {host}")

    labels = set(host.split("."))
    for label in SENSITIVE_LABELS:
        if label in labels:
            return Decision(Verdict.DROP, f"sensitive host label {label}")

    haystack = path + "?" + query
    for fragment in BLOCKED_FRAGMENTS:
        if fragment in haystack:
            return Decision(Verdict.DROP, f"sensitive path ({fragment.strip('/')})")

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


def redaction_summary(dropped: List[str]) -> List[str]:
    """Aggregate drop reasons, without repeating URLs."""
    counts: dict = {}
    for reason in dropped:
        counts[reason] = counts.get(reason, 0) + 1
    return [f"{reason} ×{count}" for reason, count in sorted(counts.items())]
