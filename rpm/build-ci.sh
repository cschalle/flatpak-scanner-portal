#!/bin/bash
# SPDX-License-Identifier: LGPL-2.1-or-later
# Builds xdg-desktop-portal, xdg-desktop-portal-gnome and xdg-desktop-portal-gtk with the scanner
# portal patches from patches/ in this repository, inside a Fedora container (as root). The Fedora
# spec files are taken from dist-git. The RPMs end up in $OUT (default rpm/out).
#
#   build-ci.sh [package...]
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
TOP=$(dirname "$HERE")
OUT=${OUT:-$HERE/out}
FEDORA=${FEDORA_RELEASE:-44}
SUFFIX=${SCANNER_RELEASE_SUFFIX:-scanner1}
RELNUM=${SCANNER_RELEASE:-100}
WORK=${WORK:-/var/tmp/scanner-rpm}

declare -A TAG=( [xdg-desktop-portal]=1.22.1 [xdg-desktop-portal-gnome]=50.0 [xdg-desktop-portal-gtk]=1.15.3 )

PKGS=("$@")
[ ${#PKGS[@]} -gt 0 ] || PKGS=(xdg-desktop-portal xdg-desktop-portal-gnome xdg-desktop-portal-gtk)

dnf -y -q install rpm-build rpmdevtools dnf-plugins-core createrepo_c git python3 >/dev/null
mkdir -p "$OUT" "$WORK"

for p in "${PKGS[@]}"; do
  top=$WORK/$p; rm -rf "$top"; mkdir -p "$top"/{SOURCES,SPECS,SRPMS,RPMS,BUILD,BUILDROOT}
  git clone -q --depth 1 -b "f$FEDORA" "https://src.fedoraproject.org/rpms/$p.git" "$WORK/dist-git-$p"
  cp "$WORK/dist-git-$p"/* "$top/SOURCES/"
  cp "$TOP/patches/$p/${TAG[$p]}"/0*.patch "$top/SOURCES/"
  echo "== $p: $(ls "$TOP/patches/$p/${TAG[$p]}" | wc -l) patches on ${TAG[$p]}"
  python3 "$HERE/patch-spec.py" "$WORK/dist-git-$p/$p.spec" "$top/SPECS/$p.spec" "$top/SOURCES" "$SUFFIX" "$p" "$RELNUM"
  rm -f "$top/SOURCES/$p.spec"

  # Packages built earlier in this run, so that the next one builds against them
  if ls "$OUT"/*.rpm >/dev/null 2>&1; then
    createrepo_c -q "$OUT"
    printf "[scanner]\nname=scanner\nbaseurl=file://%s\ngpgcheck=0\npriority=1\n" "$OUT" > /etc/yum.repos.d/scanner.repo
  fi
  dnf -y -q builddep "$top/SPECS/$p.spec" >/dev/null
  spectool -g -C "$top/SOURCES" "$top/SPECS/$p.spec" >/dev/null
  rpmbuild --define "_topdir $top" -ba "$top/SPECS/$p.spec" > "$top/rpmbuild.log" 2>&1 || { tail -60 "$top/rpmbuild.log"; exit 1; }
  cp "$top"/RPMS/*/*.rpm "$top"/SRPMS/*.rpm "$OUT/"
done

createrepo_c -q "$OUT"
ls -1 "$OUT"/*.rpm
