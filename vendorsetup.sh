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

apply_patch_file() {
    local target_dir="$1"
    local patch_file="$2"

    git -C "$target_dir" apply --ignore-whitespace "$patch_file"
}

revert_patch_file() {
    local target_dir="$1"
    local patch_file="$2"

    git -C "$target_dir" apply -R --ignore-whitespace "$patch_file"
}

detect_patch_state() {
    local target_dir="$1"
    local patch_file="$2"

    if git -C "$target_dir" apply --check --ignore-whitespace "$patch_file" >/dev/null 2>&1; then
        printf '%s\n' "not_applied"
    elif git -C "$target_dir" apply -R --check --ignore-whitespace "$patch_file" >/dev/null 2>&1; then
        printf '%s\n' "applied"
    else
        printf '%s\n' "unknown"
    fi
}

handle_patch_file() {
    local target_dir="$1"
    local patch_file="$2"
    local patch_name patch_state temp_patch

    patch_name=$(basename "$patch_file")
    temp_patch="/tmp/$patch_name.$$"

    if [ ! -f "$patch_file" ]; then
        warn "Patch file not found: $patch_file"
        return
    fi

    tr -d '\r' < "$patch_file" > "$temp_patch"
    patch_state=$(detect_patch_state "$target_dir" "$temp_patch")

    case "$patch_state" in
        not_applied)
            if is_interactive_shell; then
                if ! prompt_yes_no "Apply $patch_name?"; then
                    info "Skipped $patch_name."
                    rm -f "$temp_patch"
                    return
                fi
            else
                info "Non-interactive shell detected; applying $patch_name."
            fi

            if apply_patch_file "$target_dir" "$temp_patch"; then
                success "Applied $patch_name."
            else
                error "Failed to apply $patch_name."
            fi
            ;;
        applied)
            if is_interactive_shell; then
                if ! prompt_yes_no "Revert $patch_name?"; then
                    info "Kept $patch_name applied."
                    rm -f "$temp_patch"
                    return
                fi

                if revert_patch_file "$target_dir" "$temp_patch"; then
                    success "Reverted $patch_name."
                else
                    error "Failed to revert $patch_name."
                fi
            else
                info "Non-interactive shell detected; normalizing $patch_name."

                if revert_patch_file "$target_dir" "$temp_patch" && \
                    apply_patch_file "$target_dir" "$temp_patch"; then
                    success "Reapplied $patch_name."
                else
                    error "Failed to normalize $patch_name."
                fi
            fi
            ;;
        *)
            warn "$patch_name is not cleanly applicable or revertible; skipping."
            ;;
    esac

    rm -f "$temp_patch"
}

manage_tablet_patch() {
    local script_dir root_dir target_dir
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
        handle_patch_file "$target_dir" "$patch_file"
    done
}

manage_tablet_patch
