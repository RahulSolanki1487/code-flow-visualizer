"""The `plain_summary` of a flow: a short story, in simple language, that walks through the flow and names every step of the diagram
exactly as the diagram shows it (`auth middleware`, `POST /products`), so a non-technical reader can match each sentence to a box.

`problems(text, labels)` returns short messages; an empty list means the text is fine. The rules:
  * it exists and has a sensible length (longer flows may have a longer text);
  * it mentions every step label of the flow (navigation stubs created by `split_flow.py` are exempt);
  * apart from the step names, it contains no code: no file names, routes, code syntax or identifiers.
"""
import re

MIN_CHARS = 60
BASE_MAX_CHARS = 600
CHARS_PER_STEP = 70

FILE_RE = re.compile(r"\b[\w-]+\.(?:js|jsx|ts|tsx|cs|java|kt|py|rb|php|go|dart|json|html|yml|yaml|proto|sql|graphql)\b", re.I)
ROUTE_RE = re.compile(r"(?:^|\s)/[\w{}:.-]+(?:/[\w{}:.-]+)*|\b(?:GET|POST|PUT|PATCH|DELETE)\s+/")
SYNTAX_RE = re.compile(r"\(\)|::|=>|->|[{}\[\]<>]|`")
CAMEL_RE = re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b")
PASCAL_RE = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b")
SNAKE_RE = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b")
# well-known product and technology names that look like code identifiers but are fine in plain text
ALLOWED = {"JavaScript", "TypeScript", "GraphQL", "PostgreSQL", "MongoDB", "GitHub", "OAuth", "PayPal", "iPhone", "WhatsApp",
           "LinkedIn", "YouTube", "SharePoint", "OneDrive", "PowerBI", "DevOps"}
STUB_PREFIXES = ("continues_", "back_to_")   # navigation nodes added by split_flow.py


def step_labels(flow: dict) -> list[str]:
    """The labels a plain summary must mention: every diagram step except split_flow's navigation stubs."""
    return [n["label"] for n in flow.get("nodes", []) if n.get("label") and not str(n.get("id", "")).startswith(STUB_PREFIXES)]


def label_pattern(label: str) -> re.Pattern:
    """Whole-word, case-insensitive match of a step label (the page uses the same rule to link names to steps)."""
    return re.compile(r"(?<!\w)" + re.escape(label) + r"(?!\w)", re.I)


def mentions(text: str, label: str) -> bool:
    return bool(label_pattern(label).search(text or ""))


def without_labels(text: str, labels) -> str:
    """The text with every step label blanked out, longest first, so only the surrounding prose is left."""
    for label in sorted(set(labels), key=len, reverse=True):
        text = label_pattern(label).sub(" ", text)
    return text


def problems(text: str | None, labels=()) -> list[str]:
    text = (text or "").strip()
    labels = [l for l in labels if l]
    if not text:
        return ["missing"]
    found = []
    max_chars = BASE_MAX_CHARS + CHARS_PER_STEP * len(labels)
    if len(text) < MIN_CHARS:
        found.append(f"too short ({len(text)} chars; at least {MIN_CHARS})")
    if len(text) > max_chars:
        found.append(f"too long ({len(text)} chars; at most {max_chars} for {len(labels)} steps)")
    missing = [l for l in labels if not mentions(text, l)]
    if missing:
        shown = ", ".join(repr(l) for l in missing[:5]) + (f" and {len(missing) - 5} more" if len(missing) > 5 else "")
        found.append(f"does not mention {len(missing)} of {len(labels)} steps: {shown}")
    rest = without_labels(text, labels)
    for label, regex in (("a file name", FILE_RE), ("a URL or route", ROUTE_RE), ("code syntax", SYNTAX_RE)):
        m = regex.search(rest)
        if m:
            found.append(f"contains {label} that is not a step name: {m.group(0).strip()!r}")
    idents = [w for rx in (CAMEL_RE, PASCAL_RE, SNAKE_RE) for w in rx.findall(rest) if w not in ALLOWED]
    if idents:
        found.append(f"contains a code name that is not a step name: {idents[0]!r}")
    return found
