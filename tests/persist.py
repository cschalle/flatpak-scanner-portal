#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""A choice the user let the portal remember is there for the next run, for the scanners whose id
stays the same, and is taken back through the permission store. Run through
run-persist-c-frontend.sh."""
import os
import sys

from gi.repository import Gio, GLib

from portal_client import Client, check, failures, v

STORE = "org.freedesktop.impl.portal.PermissionStore"
APP = "org.example.Scanny"


def store(c, method, args, sig):
    return c.bus.call_sync(STORE, "/org/freedesktop/impl/portal/PermissionStore", STORE, method,
                           GLib.Variant(sig, args), None, Gio.DBusCallFlags.NONE, 20000, None).unpack()


def listed(c):
    return sorted(s[1]["name"] for s in c.call("ListScanners", ({},), "(a{sv})")[0])


def reset(c):
    """Takes every entry out of the table, which the store has no call for as a whole"""
    try:
        for i in store(c, "List", ("scanner",), "(s)")[0]:
            store(c, "Delete", ("scanner", i), "(ss)")
    except GLib.Error as e:
        if "NotFound" not in str(e):
            raise


def main():
    decline = os.environ["STAND_IN_DECLINE_PERSIST"]
    persistent = ["Fake Both Drivers", "Fake Port One", "Fake Serial One", "Fake Twin", "Fake Twin"]

    c = Client()
    reset(c)

    # Not asked for: nothing is kept
    code, results = c.select(multiple=v("b", True))
    check("a choice nobody asked to remember is made", code == 0 and len(results["scanners"]) == 8, (code, results))
    check("... and the answer says it is not remembered", results.get("persist") is False, results)
    check("... and is there in the run", len(listed(c)) == 8)
    check("... and not in the next one", listed(Client()) == [])

    # Asked for, the user says no
    open(decline, "w").close()
    code, results = Client().select(multiple=v("b", True), persist=v("b", True))
    check("a choice the user did not agree to be remembered is made", code == 0, code)
    check("... and the answer says it is not remembered", results.get("persist") is False, results)
    check("... and not in the next run", listed(Client()) == [])
    os.remove(decline)

    # Asked for, the user agrees
    c = Client()
    code, results = c.select(multiple=v("b", True), persist=v("b", True))
    check("a choice the user agreed to be remembered is made", code == 0 and len(results["scanners"]) == 8, (code, results))
    check("... and the answer says so", results.get("persist") is True, results)
    check("... all of it is there in the run", len(listed(c)) == 8)

    c2 = Client()
    check("only the scanners whose id stays the same are there in the next run, with no dialog",
          listed(c2) == persistent, listed(c2))
    ids = {s[1]["name"] + s[0]: s[0] for s in c2.call("ListScanners", ({},), "(a{sv})")[0]}
    check("... and they say persistent", all(s[1]["persistent"] for s in c2.call("ListScanners", ({},), "(a{sv})")[0]))
    other = [s[0] for s in c.call("ListScanners", ({},), "(a{sv})")[0] if not s[1]["persistent"]][0]
    check("a scanner that was not remembered is not allowed in the next run",
          c2.open_error(other) == "org.freedesktop.portal.Error.NotAllowed", c2.open_error(other))
    one = [s[0] for s in c2.call("ListScanners", ({},), "(a{sv})")[0] if s[1]["name"] == "Fake Port One"][0]
    check("a scanner that was remembered is not refused for want of a grant",
          c2.open_error(one) != "org.freedesktop.portal.Error.NotAllowed", c2.open_error(one))

    # Kept in the permission store, by the app, where the user can take it back
    ids_in_store = store(c, "List", ("scanner",), "(s)")[0]
    check("the permission store has the scanner ids of the application, and only those that stay",
          len(ids_in_store) == 5 and all(i.startswith("sane-") for i in ids_in_store), ids_in_store)
    perms = store(c, "Lookup", ("scanner", one), "(ss)")[0]
    check("it is a yes for the application", perms.get(APP) == ["yes"], perms)

    # Taken back, for one scanner and then for all
    store(c, "DeletePermission", ("scanner", one, APP), "(sss)")
    check("a scanner whose permission is taken back is gone from the next run",
          listed(Client()) == ["Fake Both Drivers", "Fake Serial One", "Fake Twin", "Fake Twin"], listed(Client()))
    check("... and cannot be opened", Client().open_error(one) == "org.freedesktop.portal.Error.NotAllowed")
    reset(c)
    check("with the table emptied nothing is remembered", listed(Client()) == [])

    # What another application was given is not this one's
    reset(c)
    c = Client()
    c.select(multiple=v("b", True), persist=v("b", True))
    store(c, "SetPermission", ("scanner", False, one, "org.example.Other", ["yes"]), "(sbssas)")
    store(c, "DeletePermission", ("scanner", one, APP), "(sss)")
    check("the grant of another application is not this one's", "Fake Port One" not in listed(Client()), listed(Client()))
    reset(c)
    c.bus.close_sync(None)

    if failures:
        print(f"{len(failures)} failed")
        return 1
    print("all persist checks passed")
    return 0


sys.exit(main())
