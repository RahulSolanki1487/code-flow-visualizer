"""Loaded automatically by every Python process that has this folder on PYTHONPATH.

skill-creator's run_eval.py evaluates queries in worker processes. On Windows those start fresh,
so the select.select() patch from run_loop_windows.py has to be applied at interpreter start-up.
"""
import os
import select

if os.name == "nt":
    from run_loop_windows import windows_select

    select.select = windows_select
