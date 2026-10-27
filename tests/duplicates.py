#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""One scanner found by two drivers is one scanner, and opening it tries the next driver when the
first cannot. Run through run-duplicates-c-frontend.sh."""
import sys

from portal_client import Client, check, failures, v


def main():
    c = Client()
    code, results = c.select(multiple=v("b", True))
    scanners = results.get("scanners", [])
    names = sorted(s[1]["name"] for s in scanners)
    check("two drivers finding one scanner is one entry, and another scanner is another",
          code == 0 and len(scanners) == 2, (code, names))
    for s in scanners:
        check("the entry has no address or bookkeeping", "physical" not in s[1] and "usb_id" not in s[1], s[1])
    film = [s for s in scanners if s[1]["name"] == "Fake Film Thing"]
    check("scanner-devices.json names a scanner and gives it capabilities",
          len(film) == 1 and film[0][1]["capabilities"] == ["film", "color"], names)
    others = [s for s in scanners if s not in film]
    check("a scanner it does not name is for documents",
          len(others) == 1 and others[0][1]["capabilities"] == ["flatbed"], others)
    listed = c.call("ListScanners", ({},), "(a{sv})")[0]
    check("ListScanners lists them the same", len(listed) == 2, listed)

    # An entry of the file that has nothing to match on is ignored, not taken for everything
    check("an unusable entry of the file does not apply to every scanner",
          not any("adf" in s[1]["capabilities"] for s in scanners), scanners)
    copier = [s for s in scanners if "Copier" in s[1]["name"] or "copier" in s[1]["name"]]
    check("the scanner both drivers found is there once", len(copier) == 1, names)
    sess = c.open(copier[0][0], "dup")
    check("it opens through the second driver, as the first cannot", bool(sess), sess)
    check("... and works", len(c.opts(sess)) > 0)

    other = c.error("OpenScanner", ([s for s in scanners if s is not copier[0]][0][0], {}), "(sa{sv})")
    check("a scanner with only the failing driver does not open", other is not None, other)
    c.bus.close_sync(None)

    if failures:
        print(f"{len(failures)} failed")
        return 1
    print("all duplicates checks passed")
    return 0


sys.exit(main())
