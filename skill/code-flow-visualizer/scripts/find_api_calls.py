#!/usr/bin/env python3
"""List the HTTP calls a frontend makes (fetch, axios, Angular HttpClient, Dart http/dio, ...).

Usage:
    python find_api_calls.py <frontend_repo> [--json]

Each call has a method, a URL pattern with dynamic parts replaced by `{}`, and flags:
  dynamic          the URL has runtime parts (`/v1/items/${id}` -> `/v1/items/{}`)
  base_unknown     the URL starts with a variable such as a base URL (`${API}/orders` -> `/orders`)
  optional_suffix  the path may continue at runtime (`'/items' + (id ? '/' + id : '')`, `/audits${query}`)
  unresolved       the first argument is not a string (e.g. a variable) so no URL could be read
Methods that are chosen at runtime (`method: id ? 'PUT' : 'POST'`) yield several methods.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from find_entry_points import SKIP_DIRS

EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".mjs", ".dart"}
VERBS = ("get", "post", "put", "patch", "delete", "head", "options")
TEST_MARKERS = (".test.", ".spec.", "__tests__", "/test/", "/tests/", "_test.dart")

# <callee>(  with an optional TypeScript generic:  apiFetch<Foo>(  /  this.http.post<{a: string}>(
CALL_RE = re.compile(
    # `\s*\.\s*` between receiver and verb: formatters put `this.http` and `.post<T>(...)` on separate lines
    r"""(?<![\w.$])((?:this\.|self\.)?(?:fetch|apiFetch|axios(?:\s*\.\s*(?:get|post|put|patch|delete|request))?|"""
    r"""\$http(?:\s*\.\s*\w+)?|(?:http|httpClient|client|api|dio|ky)(?:\s*\.\s*(?:get|post|put|patch|delete|head|request))?|"""
    r"""\w*[hH]ttp\w*\s*\.\s*(?:get|post|put|patch|delete))|request)"""
    r"""\s*(?:<[^()]*?>)?\s*\(\s*""")
METHOD_PROP_RE = re.compile(r"""\bmethod\s*:\s*([^,}\n]+)""", re.I)
QUOTED_VERB_RE = re.compile(r"""['"`](GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)['"`]""", re.I)
STRING_START = "'\"`"
PLUS_RE = re.compile(r"\s*\+")
BASE_PLUS_RE = re.compile(r"[\w.$]+(?:\([^)]*\))?\s*\+\s*")
SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://[^/]+", re.I)
REPEATED_PARAM_RE = re.compile(r"(\{\}){2,}")


def read_string_literal(text: str, i: int):
    """Read a '...', "..." or `...` literal starting at text[i]. Returns (value, end, dynamic)."""
    quote = text[i]
    out, dynamic, j = [], False, i + 1
    while j < len(text):
        c = text[j]
        if c == "\\" and j + 1 < len(text):
            out.append(text[j + 1])
            j += 2
            continue
        if quote == "`" and c == "$" and text[j + 1:j + 2] == "{":
            depth, k = 1, j + 2
            while k < len(text) and depth:
                depth += (text[k] == "{") - (text[k] == "}")
                k += 1
            out.append("{}")
            dynamic = True
            j = k
            continue
        if c == quote:
            return "".join(out), j + 1, dynamic
        if c == "\n" and quote != "`":
            return None, j, dynamic
        out.append(c)
        j += 1
    return None, j, dynamic


def skip_operand(text: str, k: int) -> int:
    """End index of one non-literal operand starting at k: `id`, `a.b.c`, `fn(x)`, `x[0]`, `(cond ? a : b)`."""
    if k < len(text) and text[k] == "(":
        return k + len(call_arguments(text, k + 1)) + 2
    m = re.compile(r"[\w.$?!]+").match(text, k)
    if not m:
        return k
    end = m.end()
    while end < len(text) and text[end] in "([":
        close = {"(": ")", "[": "]"}[text[end]]
        inner = call_arguments(text, end + 1)
        end += len(inner) + 2
        if end > len(text) or text[end - 1] != close:
            break
    return end


def read_concatenation(text: str, j: int, url: str):
    """Continue a URL built with `+` after its first literal. Returns (url, end, dynamic, optional_suffix)."""
    dynamic = optional = False
    pos = j
    while True:
        plus = PLUS_RE.match(text, pos)
        if not plus:
            break
        k = plus.end()
        while k < len(text) and text[k].isspace():
            k += 1
        if k < len(text) and text[k] in STRING_START:
            literal, end, literal_dynamic = read_string_literal(text, k)
            if literal is None:
                break
            url, dynamic, pos = url + literal, dynamic or literal_dynamic, end
            continue
        end = skip_operand(text, k)
        if end == k:
            break
        dynamic, pos = True, end
        if PLUS_RE.match(text, end):
            url += "{}"                      # more follows: this operand is a segment (or part of one)
            continue
        if url.endswith("/") and len(url) > 1:
            url += "{}"                      # '/profiles/' + username
        else:
            optional = True                  # '/items' + (...): may or may not extend the path
        break
    return url, pos, dynamic, optional


def read_url_argument(text: str, i: int):
    """Parse the first call argument. Returns (url|None, end, dynamic, base_unknown, optional_suffix)."""
    for wrapper in ("Uri.parse(", "Uri.https(", "new URL(", "Uri.http("):
        if text.startswith(wrapper, i):
            i += len(wrapper)
            break
    base_unknown = False
    if i < len(text) and text[i] not in STRING_START:
        # `BASE + '/orders'` / `this.baseUrl + "/orders"`: skip one identifier chain and the plus
        m = BASE_PLUS_RE.match(text, i)
        if not m:
            return None, i, False, False, False
        i = m.end()
        base_unknown = True
        if i >= len(text) or text[i] not in STRING_START:
            return None, i, False, False, False
    url, j, dynamic = read_string_literal(text, i)
    if url is None:
        return None, j, False, False, False
    optional_suffix = False
    if "?" in url:  # the query string is not part of the route; drop it before judging the path
        url = url.split("?", 1)[0]
    # concatenation: '/profiles/' + name + '/follow' -> /profiles/{}/follow;
    # a trailing operand after a path without a final slash may or may not extend it: '/v1/items' + (id ? '/' + id : '')
    url, j, concat_dynamic, optional_suffix = read_concatenation(text, j, url)
    dynamic = dynamic or concat_dynamic
    # a variable glued to the end of a segment (`/audits${query}`) is usually a query string
    if url.endswith("{}") and not url.endswith("/{}") and len(url) > 2:
        url, dynamic, optional_suffix = url[:-2], True, True
    url = REPEATED_PARAM_RE.sub("{}", url)
    if url.startswith("{}/"):
        url, base_unknown = url[2:], True
    return url, j, dynamic, base_unknown, optional_suffix


def call_arguments(text: str, start: int, limit: int = 1500) -> str:
    """Text of one call's argument list, from `start` to its closing paren (never into the next call)."""
    depth, i, quote = 1, start, None
    end = min(len(text), start + limit)
    while i < end:
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "'\"`":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return text[start:i]
        i += 1
    return text[start:end]


def methods_for(callee: str, args: str) -> list[str]:
    name = callee.rsplit(".", 1)[-1].lower()
    if name in VERBS:
        return [name.upper()]
    m = METHOD_PROP_RE.search(args)
    if m:
        found = sorted({v.upper() for v in QUOTED_VERB_RE.findall(m.group(1))})
        if found:
            return found
    return ["GET"]


def clean_url(url: str) -> str:
    url = url.split("?", 1)[0].split("#", 1)[0]
    url = SCHEME_RE.sub("", url)  # drop scheme://host
    return url.rstrip("/") or "/"


CONST_RE = re.compile(
    r"""(?:export\s+)?(?:static\s+)?(?:const|let|var|final)\s+(\w+)\s*(?::\s*[\w<>\[\]]+)?\s*=\s*(['"`])((?:/|\$\{)[^'"`\n]*)\2""")


def substitute_constants(text: str) -> str:
    """Inline file-level string constants (`const BASE = "/api/v1/x"`) into the URLs that use them.

    Constants may be built from earlier ones (`const BASE = `${IDENTITY}/sessions``): they are
    resolved top to bottom. A value never contains a newline, so line numbers are unchanged.
    """
    pos = 0
    while True:
        m = CONST_RE.search(text, pos)
        if not m:
            return text
        name, value = m.group(1), m.group(3)
        head, tail = text[:m.end()], text[m.end():]
        tail = tail.replace("${" + name + "}", value)                           # template literal
        tail = re.sub(r"\b" + re.escape(name) + r"\s*\+\s*(['\"`])", lambda q: q.group(1) + value, tail)  # BASE + '/x'
        tail = re.sub(r"\(\s*" + re.escape(name) + r"\s*([,)])", lambda q: '("' + value + '"' + q.group(1), tail)  # fetch(BASE)
        text = head + tail
        pos = m.end()


def find_calls_in_text(text: str, rel: str) -> list[dict]:
    text = substitute_constants(text)
    calls = []
    for m in CALL_RE.finditer(text):
        if re.search(r"(function|def|async|Future<\w+>)\s+$", text[max(0, m.start() - 24):m.start()]):
            continue  # a definition such as `export async function apiFetch<T>(`, not a call
        start_line = text.count("\n", 0, m.start()) + 1
        url, _end, dynamic, base_unknown, optional_suffix = read_url_argument(text, m.end())
        callee = re.sub(r"\s+", "", m.group(1))
        args = call_arguments(text, m.end())
        base = {"file": rel, "line": start_line, "callee": callee, "methods": methods_for(callee, args)}
        if url is None:
            calls.append({**base, "url": None, "dynamic": False, "base_unknown": False,
                          "optional_suffix": False, "unresolved": True})
            continue
        if not (url.startswith("/") or "://" in url or url.startswith("{}")):
            continue  # relative non-API strings such as 'items' are too ambiguous
        calls.append({**base, "url": clean_url(url), "dynamic": dynamic, "base_unknown": base_unknown,
                      "optional_suffix": optional_suffix, "unresolved": False})
    return calls


BASE_URL_PATTERNS = (
    # axios.create({ baseURL: 'https://host/api' }) / axios.defaults.baseURL = '/api'
    re.compile(r"""baseURL\s*[:=]\s*(['"`])([^'"`$]+)\1"""),
    # Angular / fetch interceptors: req.clone({ url: `https://host/api${req.url}` })
    re.compile(r"""\burl\s*:\s*`([^`$]*)\$\{\s*req(?:uest)?\.url\s*\}`"""),
)


def detect_base_urls(repo: Path) -> list[dict]:
    """Base paths a frontend prepends to its calls outside the call sites (axios baseURL, interceptors).

    Returns [{"base": "/api", "file": ..., "line": ...}] with scheme and host removed; hosts alone are ignored.
    """
    found = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in sorted(files):
            path = Path(root) / name
            if path.suffix.lower() not in EXTENSIONS or any(m in "/" + path.relative_to(repo).as_posix() for m in TEST_MARKERS):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "baseURL" not in text and "req.url" not in text and "request.url" not in text:
                continue
            for pattern in BASE_URL_PATTERNS:
                for m in pattern.finditer(text):
                    raw = m.group(m.lastindex if pattern is BASE_URL_PATTERNS[0] else 1)
                    base = SCHEME_RE.sub("", raw).rstrip("/")
                    if base.startswith("/") and len(base) > 1:
                        found.append({"base": base, "file": path.relative_to(repo).as_posix(),
                                      "line": text.count("\n", 0, m.start()) + 1})
    return found


def apply_base_url(calls: list[dict], base: str) -> list[dict]:
    """Prefix internal call URLs with `base` (skipping calls that already start with it)."""
    base = "/" + base.strip("/")
    out = []
    for c in calls:
        url = c.get("url")
        if url and url.startswith("/") and not (url == base or url.startswith(base + "/")):
            c = {**c, "url": base + (url if url != "/" else ""), "base_applied": base}
        out.append(c)
    return out


def scan(repo: Path, limit: int = 2000, base: str | None = None) -> list[dict]:
    calls = _scan_files(repo, limit)
    return apply_base_url(calls, base) if base else calls


def _scan_files(repo: Path, limit: int) -> list[dict]:
    out = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in sorted(files):
            path = Path(root) / name
            if path.suffix.lower() not in EXTENSIONS:
                continue
            rel = path.relative_to(repo).as_posix()
            if any(marker in "/" + rel for marker in TEST_MARKERS):
                continue
            try:
                if path.stat().st_size > 1_000_000:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            out.extend(find_calls_in_text(text, rel))
            if len(out) >= limit:
                return out[:limit]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=2000)
    args = ap.parse_args(argv)
    calls = scan(Path(args.repo), args.limit)
    if args.json:
        print(json.dumps(calls, indent=2))
        return 0
    if not calls:
        print("No HTTP calls found by heuristics. Look for the project's API client wrapper.")
        return 0
    for c in calls:
        flags = ",".join(f for f in ("dynamic", "base_unknown", "optional_suffix", "unresolved") if c[f])
        print(f"  {'/'.join(c['methods']):<12} {c['url'] or '(not a string)':<48} {c['file']}:{c['line']}"
              + (f"  [{flags}]" if flags else ""))
    print(f"\n{len(calls)} call(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
