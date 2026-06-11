#!/bin/bash
root="${ANDROID_BUILD_TOP:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
git -C "$root/frameworks/base" apply --ignore-whitespace "$d/patches/landscape-bootanim.patch" 2>/dev/null || true
git -C "$root/frameworks/base" apply --ignore-whitespace "$d/patches/tablet-fwb.patch" 2>/dev/null || true

