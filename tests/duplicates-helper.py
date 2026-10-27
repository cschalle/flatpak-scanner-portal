#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""A scanner helper for the duplicates check. `list` answers as one fake driver per run, with a
scanner that another driver finds too and one only it finds, and `session` for the fake driver's
name fails like HPLIP does for a printer that only speaks eSCL. Anything else goes to the real
helper, so that the SANE test backend opens.
"""
import os
import struct
import sys

from gi.repository import GLib


def info(vendor, model, backend, typ, physical):
    d = {
        "name": GLib.Variant("s", f"{vendor} {model}"),
        "vendor": GLib.Variant("s", vendor),
        "model": GLib.Variant("s", model),
        "backend": GLib.Variant("s", backend),
        "kind": GLib.Variant("s", "network"),
        "type": GLib.Variant("s", typ),
        "capabilities": GLib.Variant("as", []),
        "available": GLib.Variant("b", True),
        "physical": GLib.Variant("s", physical),
    }
    return d


def main():
    real = os.environ["REAL_HELPER"]
    if sys.argv[1] == "list":
        conf = open(os.path.join(os.environ["SANE_CONFIG_DIR"], "dll.conf")).read().split()
        backend = conf[0]
        if backend == "fakea":
            devices = [
                ("sane-aaaa", "fakea:copier", info("Fake", "Copier 1000", "fakea", "all-in-one", "net:192.0.2.10")),
                ("sane-bbbb", "fakea:other", info("Fake", "Other", "fakea", "all-in-one", "net:192.0.2.20")),
            ]
        elif backend == "hpaio":
            devices = [("sane-cccc", "test:0", info("Fake", "copier_1000", "hpaio", "all-in-one", "net:192.0.2.10"))]
        else:
            devices = []
        v = GLib.Variant("a(ssa{sv})", devices)
        sys.stdout.buffer.write(v.get_data_as_bytes().get_data())
        sys.stdout.flush()
        return 0
    if sys.argv[1] == "session" and sys.argv[2].startswith("fakea:"):
        reply = GLib.Variant("(ubv)", (0, False, GLib.Variant("(ss)", ("failed", "the driver cannot open it"))))
        data = reply.get_data_as_bytes().get_data()
        os.write(3, struct.pack("=I", len(data)) + data)
        return 0
    os.execv(real, [real] + sys.argv[1:])


sys.exit(main())
