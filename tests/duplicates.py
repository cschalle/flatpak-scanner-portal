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
          code == 0 and len(scanners) == 5, (code, names))
    for s in scanners:
        check("the entry has no address or bookkeeping", "physical" not in s[1] and "usb_id" not in s[1], s[1])
    film = [s for s in scanners if s[1]["name"] == "Fake Film Thing"]
    check("scanner-devices.json names a scanner and gives it capabilities",
          len(film) == 1 and film[0][1]["capabilities"] == ["film", "color"], names)
    wand = [s for s in scanners if s[1]["name"] == "Fake Wand"]
    check("a handheld scanner has the capability 'handheld' and is not taken for a flatbed",
          len(wand) == 1 and wand[0][1]["capabilities"] == ["handheld"], wand)
    for_documents = c.select(multiple=v("b", True), any_capabilities=v("as", ["flatbed", "feeder"]))[1].get("scanners", [])
    check("an application for documents is not offered it",
          "Fake Wand" not in [s[1]["name"] for s in for_documents] and len(for_documents) == 3, for_documents)
    only_wands = c.select(multiple=v("b", True), required_capabilities=v("as", ["handheld"]))[1].get("scanners", [])
    check("an application that asks for 'handheld' is offered only it",
          [s[1]["name"] for s in only_wands] == ["Fake Wand"], only_wands)
    others = [s for s in scanners if s not in film and s not in wand]
    feeder = [s for s in others if s[1]["name"] == "Fake Tie Pair"]
    others = [s for s in others if s not in feeder]
    check("a scanner it does not name is for documents",
          len(others) == 2 and all(s[1]["capabilities"] == ["flatbed"] for s in others), others)
    check("a scanner with a document feeder has the capability 'feeder'",
          len(feeder) == 1 and feeder[0][1]["capabilities"] == ["flatbed", "feeder"], feeder)
    only_feeders = c.select(multiple=v("b", True), required_capabilities=v("as", ["feeder"]))[1].get("scanners", [])
    check("an application that needs a feeder is offered only the scanner that has one",
          [s[1]["name"] for s in only_feeders] == ["Fake Tie Pair"], only_feeders)
    check("the type is the portal's word, not the driver's",
          film[0][1]["type"] == "film" and all(s[1]["type"] == "scanner" for s in others + feeder), [s[1]["type"] for s in scanners])
    listed = c.call("ListScanners", ({},), "(a{sv})")[0]
    check("ListScanners lists them the same", len(listed) == 5, listed)

    # An entry of the file that has nothing to match on is ignored, not taken for everything
    check("an unusable entry of the file does not apply to every scanner",
          not any("feeder" in s[1]["capabilities"] and s[1]["name"] != "Fake Tie Pair" for s in scanners), scanners)
    copier = [s for s in scanners if "Copier" in s[1]["name"] or "copier" in s[1]["name"]]
    check("the scanner both drivers found is there once", len(copier) == 1, names)
    sess = c.open(copier[0][0], "dup")
    check("it opens through the second driver, as the first cannot", bool(sess), sess)
    check("... and works", len(c.opts(sess)) > 0)

    other = c.open_error(film[0][0])
    check("a scanner with only the failing driver does not open", other is not None, other)

    # Two drivers of equal rank: the one whose name sorts first, however the search went. A table
    # entry that names a driver puts it first. An I/O error is not an answer to try another on.
    import os
    log = os.environ["OPEN_LOG"]
    tie = [s for s in scanners if s[1]["name"] == "Fake Tie Pair"][0]
    pinned = [s for s in scanners if s[1]["name"] == "Fake Pinned Pair"][0]
    check("a tie between drivers is settled by name", tie[1]["backend"] == "fakey", tie[1]["backend"])
    check("the table's driver comes first, whatever the others rank", pinned[1]["backend"] == "fakez", pinned[1]["backend"])
    open(log, "w").close()
    c.open_error(tie[0])
    c.open_error(pinned[0])
    tried = open(log).read().split()
    check("the first driver is tried, and after an I/O error not another", tried == ["fakey:tie", "fakez:pin"], tried)
    c.bus.close_sync(None)

    if failures:
        print(f"{len(failures)} failed")
        return 1
    print("all duplicates checks passed")
    return 0


sys.exit(main())
