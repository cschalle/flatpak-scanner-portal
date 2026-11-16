#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""The id of a scanner is the same after a replug when the portal can tell the device, and
`persistent` says so. Run through run-stable-ids-c-frontend.sh."""
import os
import sys

from portal_client import Client, check, failures, v


def listing(c):
    code, results = c.select(multiple=v("b", True))
    return code, {s[1]["name"]: s for s in results.get("scanners", [])}, results.get("scanners", [])


def main():
    flag = os.environ["STABLE_FLAG"]
    c = Client()
    code, before, all_before = listing(c)
    names = sorted(before)
    check("the search lists the scanners", code == 0, (code, names))

    def persistent(name, entries=before):
        return [s for s in all_before if s[1]["name"] == name]

    check("a scanner with a serial number is persistent", before["Fake Serial One"][1]["persistent"] is True)
    check("a scanner with a port is persistent", before["Fake Port One"][1]["persistent"] is True)
    check("a scanner found only by its address is not", before["Fake Address Only"][1]["persistent"] is False)
    check("a USB scanner with neither serial number nor port is not", before["Fake No Port"][1]["persistent"] is False)
    check("a network scanner is not, whatever the driver", before["Fake Net Printer"][1]["persistent"] is False)
    twins = persistent("Fake Twin")
    check("two scanners of a kind are two entries with their own ids, told apart by their ports",
          len(twins) == 2 and twins[0][0] != twins[1][0] and all(s[1]["persistent"] for s in twins), twins)
    both = persistent("Fake Both Drivers")
    check("a USB scanner that two drivers find is one entry and persistent",
          len(both) == 1 and both[0][1]["persistent"] is True, both)
    check("no address or bookkeeping reaches the application",
          not any(k in s[1] for s in all_before for k in ("physical", "usb_id", "usb_serial", "usb_port")))
    check("the id says nothing of how it was made",
          all(s[0].startswith("sane-") and len(s[0]) == 21 for s in all_before), [s[0] for s in all_before])

    # The same scanners after a replug: new bus address and IP address
    open(flag, "w").close()
    code, after, all_after = listing(c)
    os.remove(flag)
    check("the search after a replug lists the same scanners", code == 0 and len(all_after) == len(all_before), (code, len(all_after)))
    check("the id with a serial number is the same, though the port is not", after["Fake Serial One"][0] == before["Fake Serial One"][0])
    check("the id from a port is the same after a replug", after["Fake Port One"][0] == before["Fake Port One"][0])
    check("the id of a scanner two drivers find is the same",
          after["Fake Both Drivers"][0] == before["Fake Both Drivers"][0])
    check("the ids of the twins are the same",
          sorted(s[0] for s in all_after if s[1]["name"] == "Fake Twin") == sorted(s[0] for s in twins))
    check("the id of a scanner that is not persistent is not the same, and not claimed to be",
          after["Fake Address Only"][0] != before["Fake Address Only"][0] and not after["Fake Address Only"][1]["persistent"])
    check("the id of a USB scanner that is not persistent changes with its bus address",
          after["Fake No Port"][0] != before["Fake No Port"][0])
    check("ids of different scanners differ", len({s[0] for s in all_before}) == len(all_before))

    # A scanner is opened with the id from the first search
    check("ListScanners lists them with persistent", all("persistent" in s[1] for s in c.call("ListScanners", ({},), "(a{sv})")[0]))
    c.bus.close_sync(None)

    if failures:
        print(f"{len(failures)} failed")
        return 1
    print("all stable-ids checks passed")
    return 0


sys.exit(main())
