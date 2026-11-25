"""Runs PyInstaller (build.ps1 calls this), with Python 3.10.0's dis bug fixed first.

Python 3.10.0 forgets to reset EXTENDED_ARG after an argument-less opcode (bpo-45757, fixed in 3.10.1),
so PyInstaller's import scan stops with "IndexError: tuple index out of range". This puts back the fixed
dis._unpack_opargs for this run only; on other Python versions nothing is changed.
"""

import dis
import sys

if sys.version_info[:3] == (3, 10, 0):
    def _unpack_opargs(code):
        extended_arg = 0
        for i in range(0, len(code), 2):
            op = code[i]
            if op >= dis.HAVE_ARGUMENT:
                arg = code[i + 1] | extended_arg
                extended_arg = (arg << 8) if op == dis.EXTENDED_ARG else 0
            else:
                arg = None
                extended_arg = 0
            yield (i, op, arg)

    dis._unpack_opargs = _unpack_opargs

from PyInstaller.__main__ import run  # noqa: E402

if __name__ == "__main__":
    run()
