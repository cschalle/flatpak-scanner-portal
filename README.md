# Flatpak scanner portal

A proposal and prototype for a scanner portal, `org.freedesktop.portal.Scanner`, for
xdg-desktop-portal. It lets a sandboxed application scan without `--device=all` or
`--share=network`: the user picks a scanner in a dialog, the portal holds libsane and hands the
application the frame over a pipe. It is modelled on the Print and USB portals. SANE only, in
this first version.

This repository holds the proposal, the draft D-Bus interfaces, the conformance tests and the
patches for the three portals. The applications that use it are separate projects:

- **Negative Vibes**, a film scanning application: `../negative-vibes`. It has the portal client
  (`crates/nv-sane-portal`) and a prototype service (`crates/nv-portal-proto`).
- **GNOME Simple Scan**, ported to the draft: `../simplescan`.

## What is here

| Path | What |
|---|---|
| `docs/PROPOSAL.md` | The proposal: design, what was tested, what is open |
| `docs/org.freedesktop.portal.Scanner.xml` | The draft interface for applications |
| `docs/org.freedesktop.impl.portal.Scanner.xml` | The draft interface for the dialog backends |
| `docs/HARDWARE-TEST.md` | The run sheet for the checks on a Plustek OpticFilm 8200i |
| `tests/scenarios.py`, `portal_client.py` | The scenario checks, which run against any frontend |
| `tests/impl_auto_grant.py` | A stand-in for the dialog that grants without asking |
| `tests/run-scenarios.sh` | The checks against the prototype service |
| `tests/run-scenarios-c-frontend.sh` | The checks against the frontend in C |
| `tests/duplicates.py`, `run-duplicates-c-frontend.sh` | A scanner found by two drivers is one, and opening falls back to the next driver |
| `tests/buttons.py`, `run-buttons-c-frontend.sh`, `fakebtn/` | A scanner's buttons reach the application as ButtonEvent, against a fake SANE backend whose buttons the test presses |
| `tools/portal-hw-check.sh` | The portal against libsane on the 8200i |
| `patches/` | The scanner patches for xdg-desktop-portal, -gnome and -gtk, as files |
| `rpm/build.sh` | Builds the three portals with the patches as RPMs for Fedora 44 |

## The portal code

The frontend (`scanner.c`, `scanner-helper.c`) is a branch of a clone of xdg-desktop-portal, and
the dialogs are branches of clones of xdg-desktop-portal-gnome and xdg-desktop-portal-gtk. The
clones are kept in `../portal-research`, and `patches/<package>/` has each branch as a series of
patches:

| Package | `<release>/` | `main/` |
|---|---|---|
| xdg-desktop-portal | 1.22.1 (16 patches) | main (16) |
| xdg-desktop-portal-gnome | 50.0 (4) | main (4) |
| xdg-desktop-portal-gtk | 1.15.3 (2) | main (2) |

`<release>/` applies on that release tag and is what the RPMs are built from. `main/` applies on
the main branch at the time they were made (4907561, f613aa2 and 5409af7). Nothing is pushed to
the upstream projects yet.

## License

LGPL-2.1-or-later, the license of xdg-desktop-portal, in `COPYING`: the interface files, the tests,
the tools and the documentation. The patches are under the license of the package they patch.
Negative Vibes and Simple Scan have their own.

## Tests

The scenario checks need `dbus-run-session`, python3 with PyGObject, and libsane with its `test`
backend. Neither of them touches a real scanner or your session bus.

    # the frontend in C: XDP_BUILD is a meson build directory (-Dsane=enabled) of a patched
    # xdg-desktop-portal
    XDP_BUILD=/path/to/xdg-desktop-portal/build tests/run-scenarios-c-frontend.sh

    # the prototype service, built in the negative-vibes checkout (cargo build -p nv-portal-proto)
    NEGATIVE_VIBES_DIR=../negative-vibes tests/run-scenarios.sh

Read `docs/HARDWARE-TEST.md` before `tools/portal-hw-check.sh` is run on a scanner: opening the
stock `genesys` entry for the 8200i resets it, so the check uses its own SANE configuration; the
same page has what was seen with `genesys` and the scanner's buttons.

## Git policy

The commit rules are the ones adopted from git-stage-batch, the same as in `../negative-vibes`
and `../simplescan`.

- **No `Co-Authored-By` trailer and no other AI attribution line**, on commits or in pull
  request descriptions.
- **Subject:** `component: Summary`, at most 72 characters, in the imperative, with no trailing
  period. The component is the file, area or class the change is in.
- **Body:** lines of at most 75 characters. Declarative, present tense, starting with "This
  commit …". It explains why, not only what, and states no history that did not happen.
- **One logical change per commit.** Every commit builds on its own. Split a mixed working tree
  into commits by hunk (`git stage-batch`, or `git add -p`) and check that each result works.
- **Tests:** the message says what was tested and what was not, and claims no result before it
  has been run.
- Write the message to a file and commit with `git commit -F file`. Check the widths first, and
  do not chain the commit after a check that only prints.
- Nothing is pushed until it is asked for.
