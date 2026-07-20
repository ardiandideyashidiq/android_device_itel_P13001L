#!/bin/bash

# Copyright (C) 2026 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0

root="${ANDROID_BUILD_TOP:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$root/frameworks/base"

apply_patch() {
    local patch="$1"
    local name
    name="$(basename "$patch" .patch)"

    if [ ! -f "$patch" ]; then
        echo "[patch] $name... SKIPPED (file not found)"
        return
    fi

    if git -C "$repo" apply --check --ignore-whitespace "$patch" 2>/dev/null; then
        git -C "$repo" apply --ignore-whitespace "$patch"
        echo "[patch] $name... applied"
        return
    fi

    if git -C "$repo" apply --reverse --check --ignore-whitespace "$patch" 2>/dev/null; then
        echo "[patch] $name... already applied"
        return
    fi

    echo "[patch] $name... FAILED (context mismatch, patch may need rebasing)"
}

apply_patch "$d/patches/landscape-bootanim.patch"
apply_patch "$d/patches/tablet-fwb.patch"
