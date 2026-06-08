#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info() { printf "%b\n" "${BLUE}${BOLD}->${NC} ${BLUE}$1${NC}"; }
success() { printf "%b\n" "${GREEN}${BOLD}OK${NC} ${GREEN}$1${NC}"; }
warn() { printf "%b\n" "${YELLOW}${BOLD}!${NC} ${YELLOW}$1${NC}"; }
error() { printf "%b\n" "${RED}${BOLD}X${NC} ${RED}$1${NC}" >&2; }

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd "$script_dir/.." && pwd)
declare -a temp_files=()

cleanup() {
    local temp_file
    for temp_file in "${temp_files[@]}"; do
        rm -f "$temp_file"
    done
}

trap cleanup EXIT

resolve_root_dir() {
    if [ -n "${ANDROID_BUILD_TOP:-}" ] && [ -d "${ANDROID_BUILD_TOP}" ]; then
        printf '%s\n' "$ANDROID_BUILD_TOP"
    elif [ -d "$repo_dir/../../.." ]; then
        (cd "$repo_dir/../../.." && pwd)
    else
        pwd
    fi
}

ensure_patch_copy() {
    local patch_file="$1"
    local temp_patch

    if [ ! -f "$patch_file" ]; then
        error "Patch file not found: $patch_file"
        return 1
    fi

    temp_patch=$(mktemp "/tmp/$(basename "$patch_file").XXXXXX")
    tr -d '\r' < "$patch_file" > "$temp_patch"
    temp_files+=("$temp_patch")
    printf '%s\n' "$temp_patch"
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

apply_patch_once() {
    local target_dir="$1"
    local patch_file="$2"
    local patch_name="$3"
    local state
    state=$(detect_patch_state "$target_dir" "$patch_file")

    case "$state" in
        not_applied)
            git -C "$target_dir" apply --ignore-whitespace "$patch_file"
            success "Applied $patch_name."
            ;;
        applied)
            info "Already applied $patch_name."
            ;;
        *)
            error "$patch_name is in an unsupported state for $target_dir"
            return 1
            ;;
    esac
}

require_git_target() {
    local target_dir="$1"

    if ! git -C "$target_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        error "Required target not found: $target_dir"
        return 1
    fi
}

optional_git_target() {
    local target_dir="$1"

    if git -C "$target_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        return 0
    fi

    warn "Skipping optional target: $target_dir"
    return 1
}

apply_tablet_patches() {
    local root_dir target_dir patch_file

    root_dir=$(resolve_root_dir)
    target_dir="$root_dir/frameworks/base"
    require_git_target "$target_dir"

    for patch_file in \
        "$repo_dir/patches/landscape-bootanim.patch" \
        "$repo_dir/patches/tablet-fwb.patch"; do
        apply_patch_once "$target_dir" "$(ensure_patch_copy "$patch_file")" "$(basename "$patch_file")"
    done
}

apply_axion_sdk_patch() {
    local root_dir target_dir patch_file

    root_dir=$(resolve_root_dir)
    target_dir="$root_dir/axion_sdk"
    if ! optional_git_target "$target_dir"; then
        return 0
    fi

    patch_file="$repo_dir/patches/0001-ax_deviceinfo-use-power-profile-for-battery-capacity.patch"
    apply_patch_once "$target_dir" "$(ensure_patch_copy "$patch_file")" "$(basename "$patch_file")"
}

main() {
    local command="${1:-apply}"

    case "$command" in
        apply)
            apply_tablet_patches
            apply_axion_sdk_patch
            ;;
        *)
            error "Unsupported command: $command"
            return 1
            ;;
    esac
}

main "$@"
