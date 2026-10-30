#!/usr/bin/python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# patch-spec.py SPEC OUT SOURCES SUFFIX PACKAGE RELEASE: adds the patches in SOURCES to the Fedora spec
# file, the release suffix, and for xdg-desktop-portal the SANE build. Used by build.sh and build-ci.sh.
import glob, os, re, sys
spec, out, sources, suffix, pkg, rel = sys.argv[1:]
s = open(spec).read()
patches = sorted(os.path.basename(f) for f in glob.glob(sources + "/0*.patch"))
lines = "".join("Patch%04d: %s\n" % (i + 1, f) for i, f in enumerate(patches))
s = re.sub(r"^(Source0:.*\n)", lambda m: m.group(1) + lines, s, count=1, flags=re.M)
s = s.replace("Release: %autorelease", "Release: " + rel + "%{?dist}." + suffix).replace("Release:        %autorelease", "Release:        " + rel + "%{?dist}." + suffix)
s = s.replace("%autochangelog", "* Mon Oct 26 2026 Christian Schaller <christian.schaller@gmail.com> - %s-%s.%s\n- Add the scanner portal (prototype)\n" % ("VERSION", rel, suffix))
v = re.search(r"^Version:\s*(\S+)", s, re.M).group(1)
s = s.replace("- VERSION-", "- " + v + "-")
if pkg == "xdg-desktop-portal":
    s = s.replace("BuildRequires: pkgconfig(libsystemd)\n", "BuildRequires: pkgconfig(libsystemd)\nBuildRequires: pkgconfig(sane-backends)\n", 1)
    s = s.replace("%meson %{!?with_docs:-Ddocumentation=disabled}", "%meson -Dsane=enabled %{!?with_docs:-Ddocumentation=disabled}")
    s = s.replace("%{_libexecdir}/xdg-desktop-portal-rewrite-launchers\n", "%{_libexecdir}/xdg-desktop-portal-rewrite-launchers\n%{_libexecdir}/xdg-desktop-portal-scanner-helper\n", 1)
open(out, "w").write(s)
