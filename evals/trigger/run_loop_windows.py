#!/usr/bin/env python3
r"""Run skill-creator's description-optimization loop on Windows.

skill-creator's run_eval.py polls the `claude -p` output with select.select() on a pipe, which
raises WinError 10038 on Windows (every query then silently counts as "did not trigger"), and it
launches plain `claude`, which on Windows is an npm .cmd shim that subprocess cannot start.
This wrapper fixes both without touching skill-creator:

  * select.select() is replaced by a PeekNamedPipe-based version for pipe handles
  * the real claude.exe is put on PATH when `claude` resolves to a .cmd shim

Usage (from the repo root, which must contain a .claude folder so skill-creator finds the project):
    set PYTHONPATH=<skill-creator dir>;<repo>\evals\trigger   (its sitecustomize.py patches worker processes)
    python evals/trigger/run_loop_windows.py --eval-set evals/trigger/trigger-eval.json \\
        --skill-path skill/code-flow-visualizer --model <model-id> --max-iterations 3 --verbose
All arguments are passed to scripts.run_loop.
"""
import ctypes
import msvcrt
import os
import select as _select
import shutil
import sys
import time
from ctypes import wintypes
from pathlib import Path


def pipe_has_data_or_closed(handle: int) -> bool:
    """True if the pipe has bytes to read, or is broken/closed (a read would not block)."""
    avail = wintypes.DWORD(0)
    ok = ctypes.windll.kernel32.PeekNamedPipe(wintypes.HANDLE(handle), None, 0, None, ctypes.byref(avail), None)
    return (not ok) or avail.value > 0


def windows_select(rlist, wlist, xlist, timeout=None):
    """select.select() stand-in for pipes: polls PeekNamedPipe until ready or timeout."""
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        ready = [f for f in rlist if pipe_has_data_or_closed(msvcrt.get_osfhandle(f.fileno()))]
        if ready or (deadline is not None and time.monotonic() >= deadline):
            return ready, [], []
        time.sleep(0.05)


def ensure_real_claude_on_path() -> None:
    found = shutil.which("claude")
    if found and found.lower().endswith(".exe"):
        return
    candidates = []
    if found:
        shim_dir = Path(found).parent
        candidates.append(shim_dir / "node_modules" / "@anthropic-ai" / "claude-code" / "bin")
    for bin_dir in candidates:
        if (bin_dir / "claude.exe").is_file():
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]
            return
    sys.exit("could not find claude.exe; put the folder containing it on PATH")


def main() -> None:
    ensure_real_claude_on_path()
    _select.select = windows_select  # run_eval.py calls select.select(...) through the module
    from scripts.run_loop import main as run_loop_main  # noqa: E402
    run_loop_main()


if __name__ == "__main__":
    main()
