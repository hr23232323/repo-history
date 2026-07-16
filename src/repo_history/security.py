"""Redact likely secrets before repo content is handed to an LLM.

This is a defense-in-depth safety net, **not a guarantee**. It targets
high-confidence shapes (private keys, provider tokens with fixed prefixes,
credentials in connection strings, ``KEY = "value"`` pairs) so an accidentally
committed credential doesn't get shipped into an agent's context — and, since
users are encouraged to commit `.repo-memory/`, into their repo.

It deliberately errs toward redacting. It will not catch an arbitrary
high-entropy string with no recognizable shape; don't rely on it to make a repo
full of live credentials safe to analyze.

All patterns are linear-time (no nested quantifiers) and the private-key block
scan is length-bounded, so adversarial input can't trigger catastrophic
backtracking.
"""

from __future__ import annotations

import re

_REDACTED = "[REDACTED]"

# Well-known, unambiguous secret shapes: fixed prefixes with enough entropy that
# a match is almost certainly a real credential.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # PEM private key blocks. The body is length-bounded so a BEGIN with no END
    # can't force a quadratic rescan over adversarial input.
    (
        re.compile(
            r"-----BEGIN [A-Z ]{0,40}PRIVATE KEY-----[\s\S]{0,8000}?"
            r"-----END [A-Z ]{0,40}PRIVATE KEY-----"
        ),
        "[REDACTED PRIVATE KEY]",
    ),
    # JSON Web Tokens (header.payload.signature).
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        "[REDACTED JWT]",
    ),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED AWS KEY]"),
    # Google keys are canonically AIza + 35 chars, but a length-exact rule would
    # leak a near-miss key in full, so accept a range.
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,45}\b"), "[REDACTED GOOGLE KEY]"),
    # Stripe live keys (test keys are intentionally not redacted).
    (re.compile(r"\b[sr]k_live_[0-9A-Za-z]{16,}\b"), "[REDACTED STRIPE KEY]"),
    # OpenAI / Anthropic style keys, incl. sk-proj- and sk-ant- variants.
    (re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}\b"), "[REDACTED API KEY]"),
    (re.compile(r"\bgithub_pat_[0-9A-Za-z_]{20,}\b"), "[REDACTED GITHUB TOKEN]"),
    (re.compile(r"\bgh[posru]_[A-Za-z0-9]{20,}\b"), "[REDACTED GITHUB TOKEN]"),
    (re.compile(r"\bnpm_[0-9A-Za-z]{30,}\b"), "[REDACTED NPM TOKEN]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "[REDACTED SLACK TOKEN]"),
    (
        re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b"),
        "[REDACTED SENDGRID KEY]",
    ),
    (re.compile(r"\bBearer\s+[A-Za-z0-9\-_.=]{20,}"), f"Bearer {_REDACTED}"),
]

# Credentials embedded in a connection string: postgres://user:pa55w0rd@host.
# Keeps the scheme and username so the diff still reads sensibly.
_CONNECTION_STRING = re.compile(
    r"\b([a-zA-Z][a-zA-Z0-9+.\-]*://[^\s:/@]+:)([^\s:/@]{3,})(@)"
)

_SECRET_KEY = (
    r"api[_-]?key|secret|token|password|passwd|client[_-]?secret|access[_-]?key"
    r"|credential|private[_-]?key|auth[_-]?token|dsn"
)
# Quoted value first, so values containing spaces are fully redacted.
_ASSIGN_QUOTED = re.compile(
    rf"(?i)\b({_SECRET_KEY})\b(\s*[:=]\s*)(['\"])([^'\"\r\n]{{4,}})(['\"])"
)
_ASSIGN_BARE = re.compile(
    rf"(?i)\b({_SECRET_KEY})\b(\s*[:=]\s*)([^\s'\"\r\n]{{6,}})"
)


def scrub(text: str) -> tuple[str, int]:
    """Return ``(scrubbed_text, redaction_count)``."""
    count = 0
    for pattern, replacement in _PATTERNS:
        text, n = pattern.subn(replacement, text)
        count += n

    text, n = _CONNECTION_STRING.subn(rf"\1{_REDACTED}\3", text)
    count += n
    text, n = _ASSIGN_QUOTED.subn(rf"\1\2\3{_REDACTED}\5", text)
    count += n
    text, n = _ASSIGN_BARE.subn(rf"\1\2{_REDACTED}", text)
    count += n
    return text, count
