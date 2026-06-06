#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

timeout 10s python3 - "$repo_root" <<'PY'
import os
import pty
import select
import sys

repo_root = sys.argv[1]

env = os.environ.copy()
env["CI"] = "1"
env["VENDORSETUP_SKIP_AUTO_RUN"] = "1"

pid, fd = pty.fork()
if pid == 0:
    os.chdir(repo_root)
    os.execvpe(
        "bash",
        ["bash", "-c", "source ./vendorsetup.sh; prompt_yes_no \"CI should auto-accept\""],
        env,
    )

status = None
while True:
    ready, _, _ = select.select([fd], [], [], 0.1)
    if fd in ready:
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break

    pid_done, status = os.waitpid(pid, os.WNOHANG)
    if pid_done:
        break

if status is None:
    status = os.waitpid(pid, 0)[1]

os.close(fd)

raise SystemExit(os.waitstatus_to_exitcode(status))
PY
