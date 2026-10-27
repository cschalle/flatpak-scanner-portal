#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""The buttons of a scanner reach the application as ButtonEvent. Run through
run-buttons-c-frontend.sh, which gives the portal a SANE backend whose buttons the test presses by
writing files."""
import os
import sys

from portal_client import Client, check, failures, v

DIR = os.environ["FAKEBTN_DIR"]


def press(name, value):
    with open(os.path.join(DIR, name), "w") as f:
        f.write(value)


def main():
    press("scan", "0")
    press("intelliscan", "0")
    c = Client()
    code, results = c.select(multiple=v("b", True))
    scanners = results.get("scanners", [])
    check("the scanner with buttons is offered", code == 0 and len(scanners) == 1, (code, scanners))
    info = scanners[0][1]
    check("its info lists the buttons the portal can report, by the portal's names",
          sorted(info.get("buttons", [])) == ["extra", "scan"], info.get("buttons"))

    # Held while the session opens: that is where the scanner is, not a press
    press("scan", "1")
    sess = c.open(scanners[0][0], "btn")
    check("the scanner opens", bool(sess), sess)
    c.pump(lambda: False, 1.0)
    check("a button that was down when the session opened is not a press", not c.buttons, c.buttons)

    press("scan", "0")
    c.pump(lambda: False, 0.8)
    press("scan", "1")
    check("pressing a button gives a ButtonEvent", c.pump(lambda: len(c.buttons) >= 1, 5), c.buttons)
    if c.buttons:
        s, scanner_id, name, details = c.buttons[0]
        check("it is for the session and the scanner", s == sess and scanner_id == scanners[0][0], c.buttons[0])
        check("it has the portal's name for the button and the backend's", name == "scan" and details.get("option") == "scan", c.buttons[0])
    c.pump(lambda: False, 1.2)
    check("a button that stays down is one press", len(c.buttons) == 1, c.buttons)

    press("scan", "0")
    c.pump(lambda: False, 0.8)
    press("intelliscan", "L")
    check("another button is another event, under its own name", c.pump(lambda: len(c.buttons) >= 2, 5), c.buttons)
    if len(c.buttons) >= 2:
        check("... named as the table says", c.buttons[1][2] == "extra" and c.buttons[1][3].get("option") == "intelliscan", c.buttons[1])
    c.pump(lambda: False, 1.0)
    check("a button that latches is one press", len(c.buttons) == 2, c.buttons)

    press("scan", "1")
    check("a button pressed again is a press again", c.pump(lambda: len(c.buttons) >= 3, 5), c.buttons)

    c.bus.close_sync(None)

    if failures:
        print(f"{len(failures)} failed")
        return 1
    print("all button checks passed")
    return 0


sys.exit(main())
