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
        check("the entry is for documents", "flatbed" in s[1]["capabilities"], s[1])
    listed = c.call("ListScanners", ({},), "(a{sv})")[0]
    check("ListScanners lists them the same", len(listed) == 2, listed)

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
