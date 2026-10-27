#!/bin/bash
# SPDX-License-Identifier: LGPL-2.1-or-later
# Builds xdg-desktop-portal, xdg-desktop-portal-gnome and xdg-desktop-portal-gtk for Fedora 44 with
# the scanner portal patches, into a local repository.
#
#   build.sh [--no-pull] [package...]
#
# The Fedora spec files come from dist-git clones (checked out at f44) in $RPM_DIR/<package>. The
# patches are the commits of the scanner-* branches of the clones of the three portals in
# $CLONES, above their release tag; patches/ in this repository is the same series as files.
# The build runs in a Fedora 44 container, so nothing is installed on this machine and no
# privileges are needed. The result is $RPM_DIR/repo, with repodata.
#
#   CLONES   directory with the xdg-desktop-portal* clones (default ~/projects/portal-research)
#   RPM_DIR  directory with the dist-git clones, repo and work (default $CLONES/rpm)
set -eu
R=${CLONES:-$HOME/projects/portal-research}
HERE=${RPM_DIR:-$R/rpm}
REPO=$HERE/repo
WORK=$HERE/work
IMAGE=registry.fedoraproject.org/fedora:44
SUFFIX=${SCANNER_RELEASE_SUFFIX:-scanner1}
# Raise this for every build that is installed, so that dnf sees an upgrade
RELNUM=${SCANNER_RELEASE:-100}

declare -A TAG=( [xdg-desktop-portal]=1.22.1 [xdg-desktop-portal-gnome]=50.0 [xdg-desktop-portal-gtk]=1.15.3 )
declare -A BRANCH=( [xdg-desktop-portal]=scanner-1.22.1 [xdg-desktop-portal-gnome]=scanner-50.0 [xdg-desktop-portal-gtk]=scanner-1.15.3 )

PKGS=("$@")
[ ${#PKGS[@]} -gt 0 ] || PKGS=(xdg-desktop-portal xdg-desktop-portal-gnome xdg-desktop-portal-gtk)

mkdir -p "$REPO" "$WORK"
for p in "${PKGS[@]}"; do
  src=$R/$p; spec=$HERE/$p/$p.spec
  top=$WORK/$p; rm -rf "$top"; mkdir -p "$top"/{SOURCES,SPECS,SRPMS,RPMS,BUILD,BUILDROOT}
  n=$(git -C "$src" rev-list --count "${TAG[$p]}..${BRANCH[$p]}")
  echo "== $p: $n patches from ${TAG[$p]}..${BRANCH[$p]}"
  git -C "$src" format-patch -q --no-signature -N -o "$top/SOURCES" "${TAG[$p]}..${BRANCH[$p]}"
  # Changes not committed yet, as one more patch, when the branch is the one checked out
  if [ "$(git -C "$src" branch --show-current)" = "${BRANCH[$p]}" ] && ! git -C "$src" diff --quiet HEAD; then
    printf -v wip "%04d-working-tree.patch" $((n + 1))
    git -C "$src" diff HEAD > "$top/SOURCES/$wip"
    echo "   plus uncommitted changes as $wip"
  fi
  cp "$HERE/$p"/* "$top/SOURCES/" 2>/dev/null || true
  rm -f "$top/SOURCES/$p.spec"
  python3 - "$spec" "$top/SPECS/$p.spec" "$top/SOURCES" "$SUFFIX" "$p" "$RELNUM" <<'PY'
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
PY
  grep -E "^(Release|Patch)" "$top/SPECS/$p.spec" | sed 's/^/   /'
done

if [ "${NO_PULL:-0}" != 1 ]; then podman pull -q "$IMAGE" >/dev/null; fi
for p in "${PKGS[@]}"; do
  top=$WORK/$p
  echo "== building $p"
  podman run --rm -v "$top":/build:Z -v "$REPO":/repo:Z "$IMAGE" bash -euc '
    dnf -y -q install rpm-build rpmdevtools dnf-plugins-core createrepo_c >/dev/null
    # Packages built earlier in this run, so that the next one builds against them
    if ls /repo/*.rpm >/dev/null 2>&1; then createrepo_c -q /repo; printf "[scanner]\nname=scanner\nbaseurl=file:///repo\ngpgcheck=0\npriority=1\n" > /etc/yum.repos.d/scanner.repo; fi
    spec=$(ls /build/SPECS/*.spec)
    dnf -y -q builddep "$spec" >/dev/null
    spectool -g -C /build/SOURCES "$spec" >/dev/null
    rpmbuild --define "_topdir /build" -ba "$spec" > /build/rpmbuild.log 2>&1 || { tail -40 /build/rpmbuild.log; exit 1; }
    cp /build/RPMS/*/*.rpm /repo/
  '
done
podman run --rm -v "$REPO":/repo:Z "$IMAGE" bash -euc 'dnf -y -q install createrepo_c >/dev/null; createrepo_c -q /repo'
ls -1 "$REPO"/*.rpm
