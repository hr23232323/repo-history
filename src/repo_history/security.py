"""Redact likely secrets before repo content is handed to an LLM.

This is a defense-in-depth safety net, not a guarantee. It targets the common,
high-confidence shapes (private keys, provider tokens, ``KEY = "value"`` pairs)
so an accidentally-committed credential doesn't get shipped into an agent's
context. It deliberately errs toward redacting.
"""

from __future__ import annotations

import re

# (pattern, replacement) for well-known, unambiguous secret shapes.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED PRIVATE KEY]",
    ),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED AWS KEY]"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "[REDACTED GITHUB TOKEN]"),
    (re.compile(r"\bgh[posru]_[A-Za-z0-9]{20,}\b"), "[REDACTED GITHUB TOKEN]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "[REDACTED SLACK TOKEN]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9\-_.=]{20,}"), "Bearer [REDACTED]"),
]

# key/secret/token/password = "value" style assignments (env files, config, code).
_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|passwd|client[_-]?secret|access[_-]?key)\b"
    r"(\s*[:=]\s*)"
    r"(['\"]?)"
    r"([^\s'\"]{6,})"
    r"(\3)"
)


def _mask_assignment(match: re.Match[str]) -> str:
    key, sep, quote, _value, close = match.groups()
    return f"{key}{sep}{quote}[REDACTED]{close}"


def scrub(text: str) -> tuple[str, int]:
    """Return ``(scrubbed_text, redaction_count)``."""
    count = 0
    for pattern, replacement in _PATTERNS:
        text, n = pattern.subn(replacement, text)
        count += n
    text, n = _ASSIGNMENT.subn(_mask_assignment, text)
    count += n
    return text, count
