"""Is a flow's `plain_summary` really plain? The page shows it to non-technical readers (management), so it must not
contain code names, file names, URLs or code syntax, and it must be short enough to read in a glance.

`problems(text)` returns a list of short messages; an empty list means the text is fine.
"""
import re

MIN_CHARS = 60
MAX_CHARS = 700

FILE_RE = re.compile(r"\b[\w-]+\.(?:js|jsx|ts|tsx|cs|java|kt|py|rb|php|go|dart|json|html|yml|yaml|proto|sql|graphql)\b", re.I)
ROUTE_RE = re.compile(r"(?:^|\s)/[\w{}:.-]+(?:/[\w{}:.-]+)*|\b(?:GET|POST|PUT|PATCH|DELETE)\s+/")
SYNTAX_RE = re.compile(r"\(\)|::|=>|->|[{}\[\]<>]|`")
CAMEL_RE = re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b")
PASCAL_RE = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b")
SNAKE_RE = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b")
# well-known product and technology names that look like code identifiers but are fine in plain text
ALLOWED = {"JavaScript", "TypeScript", "GraphQL", "PostgreSQL", "MongoDB", "GitHub", "OAuth", "PayPal", "iPhone", "WhatsApp",
           "LinkedIn", "YouTube", "SharePoint", "OneDrive", "PowerBI", "DevOps"}


def problems(text: str | None) -> list[str]:
    text = (text or "").strip()
    if not text:
        return ["missing"]
    found = []
    if len(text) < MIN_CHARS:
        found.append(f"too short ({len(text)} chars; at least {MIN_CHARS})")
    if len(text) > MAX_CHARS:
        found.append(f"too long ({len(text)} chars; at most {MAX_CHARS})")
    for label, regex in (("a file name", FILE_RE), ("a URL or route", ROUTE_RE), ("code syntax", SYNTAX_RE)):
        m = regex.search(text)
        if m:
            found.append(f"contains {label}: {m.group(0).strip()!r}")
    idents = [w for rx in (CAMEL_RE, PASCAL_RE, SNAKE_RE) for w in rx.findall(text) if w not in ALLOWED]
    if idents:
        found.append(f"contains a code name: {idents[0]!r}")
    return found
