#!/bin/bash
# SPDX-License-Identifier: LGPL-2.1-or-later
# Run persist.py against the frontend written in C for xdg-desktop-portal: a choice that is
# remembered is there for the next run, through the permission store, and is taken back with it.
# Applications get an id from the test hook, since a host application has none and nothing is kept
# for it. The helper is the one of the stable-ids check, whose scanners are some with an id that
# stays the same and some without; the dialog is a stand-in that agrees to be remembered unless
# the file STAND_IN_DECLINE_PERSIST exists.
#
#   XDP_BUILD=/path/to/xdg-desktop-portal/build tests/run-duplicates-c-frontend.sh
#
# XDP_BUILD is a meson build directory of the scanner-frontend branch (build it with
# -Dsane=enabled).
set -e
: "${XDP_BUILD:?set XDP_BUILD to the xdg-desktop-portal build directory}"
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/.." && pwd)
export XDP_BUILD here root PYTHONUNBUFFERED=1
exec dbus-run-session -- bash -c '
  tmp=$(mktemp -d)
  mkdir "$tmp/portals" "$tmp/sane"
  printf "ida\nidb\n" > "$tmp/sane/dll.conf"
  cat > "$tmp/portals/nvtest.portal" <<PORTAL
[portal]
DBusName=org.freedesktop.impl.portal.desktop.nvtest
Interfaces=org.freedesktop.impl.portal.Scanner
UseIn=nvtest
PORTAL
  # The portal reads what it knows about scanners from a data directory. This file names the second
  # fake scanner as a film scanner, has an entry that cannot be used, and keeps the default ranks.
  mkdir -p "$tmp/share/xdg-desktop-portal"
  cat > "$tmp/share/xdg-desktop-portal/scanner-devices.json" <<JSON
{
  "version": 1,
  "scanners": [
    { "capabilities": ["feeder"] },
    { "model_contains": "tie pair", "capabilities": ["flatbed", "feeder"] },
    { "model_contains": "other", "name": "Fake Film Thing", "capabilities": ["film", "color"] },
    { "model_contains": "pinned", "driver": "fakez", "capabilities": ["flatbed"] }
  ],
  "driver_ranks": { "_comment": "not a number", "fakea": 0, "hpaio": 8 }
}
JSON
  export XDG_DATA_DIRS=$tmp/share:/usr/local/share:/usr/share
  export SANE_CONFIG_DIR=$tmp/sane XDG_CURRENT_DESKTOP=nvtest XDG_DESKTOP_PORTAL_DIR=$tmp/portals
  # The frontend starts the permission store and the document portal; keep them off the real data
  export XDG_DATA_HOME=$tmp/data XDG_STATE_HOME=$tmp/state XDG_CACHE_HOME=$tmp/cache
  # The sources moved from src/ to desktop-portal/ after 1.22, so a build of either has it
  for XDP_BIN in "$XDP_BUILD/desktop-portal" "$XDP_BUILD/src"; do [ -x "$XDP_BIN/xdg-desktop-portal" ] && break; done
  export REAL_HELPER="$XDP_BIN/xdg-desktop-portal-scanner-helper"
  export XDP_SCANNER_HELPER=$here/stable-ids-helper.py
  export STABLE_FLAG=$tmp/replugged
  export XDG_DESKTOP_PORTAL_TEST_APP_INFO_KIND=host XDG_DESKTOP_PORTAL_TEST_HOST_APPID=org.example.Scanny
  export STAND_IN_DECLINE_PERSIST=$tmp/decline
  export PORTAL_NAME=org.freedesktop.portal.Desktop
  python3 "$here/impl_auto_grant.py" org.freedesktop.impl.portal.desktop.nvtest \
      "$root/docs/org.freedesktop.impl.portal.Scanner.xml" > "$tmp/backend.log" 2>&1 &
  backend=$!
  "$XDP_BIN/xdg-desktop-portal" -r > "$tmp/frontend.log" 2>&1 &
  frontend=$!
  trap "kill $backend $frontend 2>/dev/null; wait 2>/dev/null; rm -rf $tmp" EXIT
  for i in $(seq 100); do
    gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
        --method org.freedesktop.DBus.NameHasOwner org.freedesktop.portal.Desktop 2>/dev/null | grep -q true && break
    sleep 0.1
  done
  python3 "$here/persist.py" || { echo "--- frontend log"; tail -20 "$tmp/frontend.log"; exit 1; }
'
