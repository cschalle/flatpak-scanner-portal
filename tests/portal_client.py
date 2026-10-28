# SPDX-License-Identifier: LGPL-2.1-or-later
"""Minimal blocking D-Bus client for the prototype scanner portal (Gio), shared by the
scenario checks and the hardware checks."""
import os, sys, time
import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

NAME = os.environ.get("PORTAL_NAME", "org.freedesktop.NvPortalProto")
PATH = "/org/freedesktop/portal/desktop"
IFACE = "org.freedesktop.portal.Scanner"
failures = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ((" -- " + str(detail)) if detail and not ok else ""))
    if not ok:
        failures.append(label)


class Client:
    def __init__(self):
        # A private connection each: bus_get_sync would share one per process, and the
        # tests need clients that are different apps to the portal.
        addr = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
        self.bus = Gio.DBusConnection.new_for_address_sync(addr, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
        self.me = self.bus.get_unique_name()
        self.events = []
        self.bus.signal_subscribe(NAME, IFACE, "FrameEvent", PATH, None, Gio.DBusSignalFlags.NONE, self._on_frame)
        self.buttons = []
        self.bus.signal_subscribe(NAME, IFACE, "ButtonEvent", PATH, None, Gio.DBusSignalFlags.NONE, self._on_button)
        self.bus.signal_subscribe(NAME, "org.freedesktop.portal.Session", "Closed", None, None, Gio.DBusSignalFlags.NONE, self._on_closed)
        self.closed = []
        self.n = 0

    def _on_frame(self, _c, _s, _p, _i, _n, params):
        sess, state, details = params.unpack()
        self.events.append((sess, state, details))

    def _on_button(self, _c, _s, _p, _i, _n, params):
        self.buttons.append(params.unpack())

    def _on_closed(self, _c, _s, path, *_):
        self.closed.append(path)

    def call(self, method, args, sig, iface=IFACE, path=PATH):
        """Returns the unpacked reply, or raises GLib.Error."""
        return self.bus.call_sync(NAME, path, iface, method, GLib.Variant(sig, args), None, Gio.DBusCallFlags.NONE, 20000, None).unpack()

    def error(self, *a, **k):
        try:
            self.call(*a, **k)
        except GLib.Error as e:
            return Gio.DBusError.get_remote_error(e) or str(e)
        return None

    def select(self, **opts):
        self.n += 1
        token = f"sel{self.n}"
        sig_path = f"{PATH}/request/{self.me[1:].replace('.', '_')}/{token}"
        got = []
        sub = self.bus.signal_subscribe(NAME, "org.freedesktop.portal.Request", "Response", sig_path, None, Gio.DBusSignalFlags.NONE, lambda *a: got.append(a[-1].unpack()))
        o = {"handle_token": GLib.Variant("s", token)}
        o.update(opts)
        t0 = time.time()
        self.call("SelectScanners", ("", o), "(sa{sv})")
        self.last_select_call_seconds = time.time() - t0
        self.pump(lambda: got)
        self.bus.signal_unsubscribe(sub)
        code, results = got[0]
        return code, results

    def open_response(self, sid, token=None, timeout=65, cancel_after=None):
        """OpenScanner is a request: returns (response code, results), or raises GLib.Error if the
        call itself is refused (NotAllowed)."""
        self.n += 1
        handle_token = f"open{self.n}"
        sig_path = f"{PATH}/request/{self.me[1:].replace('.', '_')}/{handle_token}"
        got = []
        sub = self.bus.signal_subscribe(NAME, "org.freedesktop.portal.Request", "Response", sig_path, None, Gio.DBusSignalFlags.NONE, lambda *a: got.append(a[-1].unpack()))
        o = {"handle_token": GLib.Variant("s", handle_token)}
        if token:
            o["session_handle_token"] = GLib.Variant("s", token)
        try:
            t0 = time.time()
            (handle,) = self.call("OpenScanner", (sid, o), "(sa{sv})")
            self.last_open_call_seconds = time.time() - t0
            if cancel_after is not None:
                # Give up on the request: no Response follows, and what was opened is let go
                self.pump(lambda: got, cancel_after)
                self.call("Close", (), "()", iface="org.freedesktop.portal.Request", path=handle)
                self.pump(lambda: False, 4)
                return got[0] if got else None
            self.pump(lambda: got, timeout)
        finally:
            self.bus.signal_unsubscribe(sub)
        return got[0]

    def open(self, sid, token=None):
        code, results = self.open_response(sid, token)
        if code != 0:
            raise GLib.Error(f"{results.get('error')}: {results.get('message')}")
        return results["session_handle"]

    def open_error(self, sid, token=None):
        """The name of the error OpenScanner gives, as a D-Bus error would be named, or None if it opens."""
        try:
            code, results = self.open_response(sid, token)
        except GLib.Error as e:
            return Gio.DBusError.get_remote_error(e) or str(e)
        if code == 0:
            self.call("Close", (), "()", iface="org.freedesktop.portal.Session", path=results["session_handle"])
            return None
        return "org.freedesktop.portal.Error." + results.get("error", "failed").capitalize()

    def opts(self, sess):
        (d,) = self.call("GetOptions", (sess, {}), "(oa{sv})")
        return d

    def set(self, sess, pairs):
        # ordered a(sv): (name, variant)
        vals = [(k, v) for k, v in pairs]
        return self.call("SetOptions", (sess, vals, {}), "(oa(sv)a{sv})")

    def pump(self, pred, timeout=15):
        end = time.time() + timeout
        ctx = GLib.MainContext.default()
        while not pred() and time.time() < end:
            ctx.iteration(False)
            time.sleep(0.005)
        return pred()

    def start_frame(self, sess):
        res = self.bus.call_with_unix_fd_list_sync(NAME, PATH, IFACE, "StartFrame", GLib.Variant("(oa{sv})", (sess, {})), None, Gio.DBusCallFlags.NONE, 20000, None, None)
        reply, fdl = res
        handle, self.last_frame = reply.unpack()
        fd = fdl.get(handle)
        return fd

    def cancel(self, sess, frame=None):
        """Cancel() the frame StartFrame returned last, or the one given."""
        self.call("Cancel", (sess, self.last_frame if frame is None else frame), "(ou)")

    def wait_state(self, sess, states, start=0, timeout=20):
        def find():
            for i in range(start, len(self.events)):
                if self.events[i][0] == sess and self.events[i][1] in states:
                    return i
            return None
        self.pump(lambda: find() is not None, timeout)
        i = find()
        return (i, self.events[i]) if i is not None else (None, None)


def v(sig, x):
    return GLib.Variant(sig, x)
