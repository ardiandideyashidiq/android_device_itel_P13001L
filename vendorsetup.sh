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
    local script_dir root_dir target_dir
    local patch_file patch_name patch_state temp_patch
    local -a patch_files

    script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

    if [ -n "$ANDROID_BUILD_TOP" ] && [ -d "$ANDROID_BUILD_TOP/frameworks/base/.git" ]; then
        root_dir="$ANDROID_BUILD_TOP"
    elif [ -d "$script_dir/../../../frameworks/base/.git" ]; then
        root_dir=$(cd "$script_dir/../../.." && pwd)
    else
        root_dir=$(pwd)
    fi

    target_dir="$root_dir/frameworks/base"

    if [ ! -d "$target_dir/.git" ]; then
        warn "Patch target not found: $target_dir"
        return
    fi

    patch_files=(
        "$script_dir/patches/0001-tablet-hardcode-landscape-default-rotation.patch"
        "$script_dir/patches/tablet-fwb.patch"
    )

    for patch_file in "${patch_files[@]}"; do
        patch_name=$(basename "$patch_file")
        temp_patch="/tmp/$patch_name.$$"

        if [ ! -f "$patch_file" ]; then
            warn "Patch file not found: $patch_file"
            continue
        fi

        tr -d '\r' < "$patch_file" > "$temp_patch"

        if git -C "$target_dir" apply --check --ignore-whitespace "$temp_patch" >/dev/null 2>&1; then
            patch_state="not_applied"
        elif git -C "$target_dir" apply -R --check --ignore-whitespace "$temp_patch" >/dev/null 2>&1; then
            patch_state="applied"
        else
            warn "$patch_name is not cleanly applicable or revertible; skipping."
            rm -f "$temp_patch"
            continue
        fi

        if [ "$patch_state" = "not_applied" ]; then
            if is_interactive_shell; then
                if ! prompt_yes_no "Apply $patch_name?"; then
                    info "Skipped $patch_name."
                    rm -f "$temp_patch"
                    continue
                fi
            else
                info "Non-interactive shell detected; applying $patch_name."
            fi

            if git -C "$target_dir" apply --ignore-whitespace "$temp_patch"; then
                success "Applied $patch_name."
            else
                error "Failed to apply $patch_name."
            fi
        else
            if ! is_interactive_shell; then
                info "$patch_name is already applied; leaving it in place."
                rm -f "$temp_patch"
                continue
            fi

            if ! prompt_yes_no "Revert $patch_name?"; then
                info "Kept $patch_name applied."
                rm -f "$temp_patch"
                continue
            fi

            if git -C "$target_dir" apply -R --ignore-whitespace "$temp_patch"; then
                success "Reverted $patch_name."
            else
                error "Failed to revert $patch_name."
            fi
        fi

        rm -f "$temp_patch"
    done
}

manage_tablet_patch
