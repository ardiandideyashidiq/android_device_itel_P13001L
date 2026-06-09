#!/bin/bash

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
patch_runner="$repo_dir/scripts/vendor-patches.sh"

if [ "${VENDORSETUP_SKIP_AUTO_RUN:-0}" != "1" ]; then
    if [ ! -x "$patch_runner" ]; then
        echo "vendorsetup.sh: missing patch runner: $patch_runner" >&2
        return 1 2>/dev/null || exit 1
    fi

    bash "$patch_runner" apply
fi
