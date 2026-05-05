#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info() { printf "%b\n" "${BLUE}${BOLD}->${NC} ${BLUE}$1${NC}"; }
success() { printf "%b\n" "${GREEN}${BOLD}OK${NC} ${GREEN}$1${NC}"; }
warn() { printf "%b\n" "${YELLOW}${BOLD}!${NC} ${YELLOW}$1${NC}"; }
error() { printf "%b\n" "${RED}${BOLD}X${NC} ${RED}$1${NC}"; }

is_interactive_shell() {
    [ -t 0 ] && [ -t 1 ]
}

prompt_yes_no() {
    local prompt="$1"
    local reply

    printf "%s [y/N] " "$prompt"
    IFS= read -r reply || return 1
    case "$reply" in
        [Yy]|[Yy][Ee][Ss])
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

manage_tablet_patch() {
    local script_dir root_dir target_dir patch_file patch_state temp_patch

    script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

    if [ -n "$ANDROID_BUILD_TOP" ] && [ -d "$ANDROID_BUILD_TOP/frameworks/base/.git" ]; then
        root_dir="$ANDROID_BUILD_TOP"
    elif [ -d "$script_dir/../../../frameworks/base/.git" ]; then
        root_dir=$(cd "$script_dir/../../.." && pwd)
    else
        root_dir=$(pwd)
    fi

    target_dir="$root_dir/frameworks/base"
    patch_file="$script_dir/patches/tablet-fwb.patch"
    temp_patch="/tmp/tablet-fwb.patch.$$"

    if [ ! -f "$patch_file" ]; then
        warn "Patch file not found: $patch_file"
        return
    fi

    if [ ! -d "$target_dir/.git" ]; then
        warn "Patch target not found: $target_dir"
        return
    fi

    tr -d '\r' < "$patch_file" > "$temp_patch"

    if git -C "$target_dir" apply --check --ignore-whitespace "$temp_patch" >/dev/null 2>&1; then
        patch_state="not_applied"
    elif git -C "$target_dir" apply -R --check --ignore-whitespace "$temp_patch" >/dev/null 2>&1; then
        patch_state="applied"
    else
        warn "tablet-fwb.patch is not cleanly applicable or revertible; skipping."
        rm -f "$temp_patch"
        return
    fi

    if [ "$patch_state" = "not_applied" ]; then
        if is_interactive_shell; then
            if ! prompt_yes_no "Apply tablet-fwb.patch?"; then
                info "Skipped tablet-fwb.patch."
                rm -f "$temp_patch"
                return
            fi
        else
            info "Non-interactive shell detected; applying tablet-fwb.patch."
        fi

        if git -C "$target_dir" apply --ignore-whitespace "$temp_patch"; then
            success "Applied tablet-fwb.patch."
        else
            error "Failed to apply tablet-fwb.patch."
        fi
    else
        if ! is_interactive_shell; then
            info "tablet-fwb.patch is already applied; leaving it in place."
            rm -f "$temp_patch"
            return
        fi

        if ! prompt_yes_no "Revert tablet-fwb.patch?"; then
            info "Kept tablet-fwb.patch applied."
            rm -f "$temp_patch"
            return
        fi

        if git -C "$target_dir" apply -R --ignore-whitespace "$temp_patch"; then
            success "Reverted tablet-fwb.patch."
        else
            error "Failed to revert tablet-fwb.patch."
        fi
    fi

    rm -f "$temp_patch"
}

manage_tablet_patch
