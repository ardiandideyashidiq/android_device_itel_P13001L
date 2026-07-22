#!/bin/bash

# Copyright (C) 2026 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0

root="${ANDROID_BUILD_TOP:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$root/frameworks/base"

apply_patch() {
    local patch="$1"
    local target_repo="${2:-$repo}"
    local name
    name="$(basename "$patch" .patch)"

    if [ ! -f "$patch" ]; then
        echo "[patch] $name... SKIPPED (file not found)"
        return
    fi

    if git -C "$target_repo" apply --check --ignore-whitespace "$patch" 2>/dev/null; then
        git -C "$target_repo" apply --ignore-whitespace "$patch"
        echo "[patch] $name... applied"
        return
    fi

    if git -C "$target_repo" apply --reverse --check --ignore-whitespace "$patch" 2>/dev/null; then
        echo "[patch] $name... already applied"
        return
    fi

    echo "[patch] $name... FAILED (context mismatch, patch may need rebasing)"
}

# ── frameworks/base ──
apply_patch "$d/patches/landscape-bootanim.patch"
apply_patch "$d/patches/tablet-fwb.patch"

# ── system/core (fenrir) ──
apply_patch "$d/patches/0001-libfs_avb-Allow-LKs-patched-with-fenrir-to-boot-on-A.patch" "$root/system/core"
apply_patch "$d/patches/0002-fastbootd-Always-return-false-for-GetDeviceLockStatu.patch" "$root/system/core"
