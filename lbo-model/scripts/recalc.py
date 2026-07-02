#!/usr/bin/env python3
"""Recalculate the formulas in an .xlsx and write the cached values back.

openpyxl writes formula *strings* (`=B5*B6`) but never evaluates them, so a
freshly built workbook has no cached results — Excel shows the formulas but the
values read as 0/blank until the file is opened in a spreadsheet app. This helper
round-trips the file through LibreOffice headless, which recalculates on load and
persists the computed values on save.

Usage:
    python3 scripts/recalc.py <file.xlsx>

Requires LibreOffice (`soffice`) on PATH — present on the Rebyte VM. On a machine
without it the script exits non-zero with a clear message instead of silently
delivering an unrecalculated file.
"""
import os
import shutil
import subprocess
import sys
import tempfile


def recalc(path: str) -> None:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        sys.exit(
            "recalc.py: LibreOffice (soffice) not found on PATH.\n"
            "Install it, or open the workbook once in Excel to cache values."
        )
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        sys.exit(f"recalc.py: no such file: {path}")

    with tempfile.TemporaryDirectory() as tmp:
        # Converting to xlsx forces a recalc on load; the re-saved file carries
        # the computed values. Use an isolated user profile so headless runs do
        # not collide with a desktop LibreOffice session.
        profile = os.path.join(tmp, "profile")
        subprocess.run(
            [
                soffice,
                "--headless",
                "--calc",
                f"-env:UserInstallation=file://{profile}",
                "--convert-to",
                "xlsx:Calc MS Excel 2007 XML",
                "--outdir",
                tmp,
                path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        out = os.path.join(tmp, os.path.basename(path))
        if not os.path.isfile(out):
            sys.exit("recalc.py: LibreOffice produced no output — recalc failed.")
        shutil.move(out, path)
    print(f"recalc.py: recalculated {path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: recalc.py <file.xlsx>")
    recalc(sys.argv[1])
