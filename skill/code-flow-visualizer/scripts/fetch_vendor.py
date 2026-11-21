#!/usr/bin/env python3
"""Download Bootstrap, Mermaid and svg-pan-zoom into assets/vendor/ so that
`render_page.py --offline` produces a page that works without internet.

Usage:
    python fetch_vendor.py
"""
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_page import CDN, VENDOR, VENDOR_FILES  # noqa: E402


def main():
    VENDOR.mkdir(parents=True, exist_ok=True)
    for key, url in CDN.items():
        dest = VENDOR / VENDOR_FILES[key]
        print(f"downloading {url}")
        with urllib.request.urlopen(url, timeout=60) as resp:
            dest.write_bytes(resp.read())
        print(f"  -> {dest} ({dest.stat().st_size // 1024} KB)")
    print("done. Use: python render_page.py flow.json -o flow.html --offline")


if __name__ == "__main__":
    main()
