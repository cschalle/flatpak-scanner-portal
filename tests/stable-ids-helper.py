#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""A scanner helper for the stable-ids check. `list` answers, per fake driver, with scanners that
have a serial number, a port, a name from the network, or nothing that stays the same. While the
flag file exists the scanners are as after a replug: the bus address and the IP address are not
what they were, and nothing else is. Anything but `list` goes to the real helper.
"""
import os
import sys

from gi.repository import GLib


def info(vendor, model, backend, physical, usb_id=None, serial=None, port=None):
    d = {
        "name": GLib.Variant("s", f"{vendor} {model}"),
        "vendor": GLib.Variant("s", vendor),
        "model": GLib.Variant("s", model),
        "backend": GLib.Variant("s", backend),
        "kind": GLib.Variant("s", "usb" if physical.startswith("usb") else "network"),
        "type": GLib.Variant("s", "flatbed scanner"),
        "capabilities": GLib.Variant("as", []),
        "available": GLib.Variant("b", True),
        "physical": GLib.Variant("s", physical),
    }
    for key, value in (("usb_id", usb_id), ("usb_serial", serial), ("usb_port", port)):
        if value is not None:
            d[key] = GLib.Variant("s", value)
    return d


def main():
    real = os.environ["REAL_HELPER"]
    if sys.argv[1] != "list":
        os.execv(real, [real] + sys.argv[1:])
    moved = os.path.exists(os.environ["STABLE_FLAG"])
    bus = 7 if moved else 1      # what a replug changes
    ip = "192.0.2.77" if moved else "192.0.2.5"
    conf = open(os.path.join(os.environ["SANE_CONFIG_DIR"], "dll.conf")).read().split()
    backend = conf[0]
    devices = []
    if backend == "ida":
        devices = [
            # A serial number: the port does not matter
            ("a1", "ida:serial", info("Fake", "Serial One", "ida", f"usb:{bus}:5", "0001:0001", "ABCD1234", "1-1" if not moved else "1-9")),
            # No serial number: the port
            ("a2", "ida:port", info("Fake", "Port One", "ida", f"usb:{bus}:6", "0001:0002", None, "1-2")),
            # Two of a kind whose serial number is the same: the helper has left it out, so ports
            ("a3", "ida:twin1", info("Fake", "Twin", "ida", f"usb:{bus}:7", "0001:0003", None, "1-3")),
            ("a4", "ida:twin2", info("Fake", "Twin", "ida", f"usb:{bus}:8", "0001:0003", None, "1-4")),
            # A scanner that is found by an address only
            ("a5", "ida:addr", info("Fake", "Address Only", "ida", f"net:{ip}")),
            # A USB scanner the helper could not read the port of
            ("a6", "ida:noport", info("Fake", "No Port", "ida", f"usb:{bus}:11", "0001:0005")),
            # A USB scanner of an id that two drivers find: the same id from both
            ("a7", "ida:both", info("Fake", "Both Drivers", "ida", f"usb:{bus}:12", "0001:0006", "ZZZ99999", "1-5")),
            # A network scanner, found by two drivers
            ("a8", "ida:escl", info("Fake", "Net Printer", "ida", "net:192.0.2.20")),
        ]
    elif backend == "idb":
        devices = [
            ("b1", "idb:printer", info("Fake", "Net Printer", "idb", "net:192.0.2.20")),
            ("b2", "idb:both", info("Fake", "Both Drivers", "idb", f"usb:{bus}:12", "0001:0006", "ZZZ99999", "1-5")),
        ]
    v = GLib.Variant("a(ssa{sv})", devices)
    sys.stdout.buffer.write(v.get_data_as_bytes().get_data())
    sys.stdout.flush()
    return 0


sys.exit(main())
