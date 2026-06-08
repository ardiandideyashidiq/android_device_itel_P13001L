#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

python3 - "$repo_root" <<'PY'
import os
import pathlib
import pty
import select
import subprocess
import sys
import tempfile
import textwrap


REPO_ROOT = pathlib.Path(sys.argv[1]).resolve()
PATCH_RUNNER = REPO_ROOT / "scripts" / "vendor-patches.sh"


def run(cmd, *, cwd=None, env=None, timeout=20, check=True):
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=check,
    )


def write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")


def git_init(path: pathlib.Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q"], cwd=path)
    run(["git", "config", "user.name", "Test User"], cwd=path)
    run(["git", "config", "user.email", "test@example.com"], cwd=path)


def seed_frameworks_base(path: pathlib.Path) -> None:
    git_init(path)
    write(
        path / "cmds/bootanimation/BootAnimation.cpp",
        """
        static int defaultRotation(const std::string& syspropValue) {
            } else if (syspropValue == "ORIENTATION_270") {
                return ui::ROTATION_270;
            }
            return ui::ROTATION_0;
        }

        void BootAnimation::projectSceneToWindow(const Display& display) {
        }
        """,
    )
    write(
        path / "services/core/java/com/android/server/wm/DisplayRotation.java",
        """
        public class DisplayRotation {
            int readDefaultRotation() {
                } else if (syspropValue.equals("ORIENTATION_270")) {
                    return Surface.ROTATION_270;
                }
                return Surface.ROTATION_0;
            }

            private int readRotation(int resID) {
                return 0;
            }

            int rotationForOrientation() {
                final int lastOrientation = mLastOrientation;
                @Surface.Rotation
                int rotation = rotationForOrientation(lastOrientation, oldRotation);
                // Use the saved rotation for tabletop mode, if set.
                if (mFoldController != null && mFoldController.shouldRevertOverriddenRotation()) {
                    int prevRotation = rotation;
                }
                return rotation;
            }
        }
        """,
    )
    write(
        path / "packages/SystemUI/src/com/android/systemui/shade/QuickSettingsControllerImpl.java",
        """
        public class QuickSettingsControllerImpl implements QuickSettingsController, Dumpable {
            boolean shouldQuickSettingsIntercept(float x, float y, float yDiff, boolean onHeader) {
                if (getExpanded()) {
                    return onHeader || (yDiff < 0 && isTouchInQsArea(x, y));
                } else {
                    return onHeader;
                }
            }

        }
        """,
    )


def seed_axion_sdk(path: pathlib.Path) -> None:
    git_init(path)
    write(
        path / "ax_deviceinfo/src/com/android/axion/deviceinfo/DeviceInfoProvider.kt",
        """
        object DeviceInfoProvider {
            }

            fun getBatteryCapacity(context: Context): String {
                val batteryIntent = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
                val designCapacityUah = batteryIntent?.getIntExtra(BatteryManager.EXTRA_DESIGN_CAPACITY, -1) ?: -1
                val capacityMah = if (designCapacityUah > 0) {
                    designCapacityUah / 1000
                } else {
                    PowerProfile(context).getAveragePower(PowerProfile.POWER_BATTERY_CAPACITY).roundToInt()
                }
                return "$capacityMah mAh"
            }

            fun getScreenSize(): String {
                return "13.2"
            }
        }
        """,
    )


def run_patch_runner(workspace: pathlib.Path, *args: str, check=True):
    return run(
        ["bash", str(PATCH_RUNNER), *args],
        cwd=REPO_ROOT,
        env={**os.environ, "ANDROID_BUILD_TOP": str(workspace)},
        check=check,
    )


def run_source_with_pty(workspace: pathlib.Path, timeout_seconds: float = 5.0):
    env = {**os.environ, "ANDROID_BUILD_TOP": str(workspace)}
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(REPO_ROOT)
        os.execvpe("bash", ["bash", "-c", "source ./vendorsetup.sh"], env)

    output = bytearray()
    exit_code = None
    timed_out = False
    while True:
        ready, _, _ = select.select([fd], [], [], 0.1)
        if fd in ready:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            output.extend(chunk)

        done_pid, status = os.waitpid(pid, os.WNOHANG)
        if done_pid:
            exit_code = os.waitstatus_to_exitcode(status)
            break

        timeout_seconds -= 0.1
        if timeout_seconds <= 0:
            timed_out = True
            os.kill(pid, 15)
            _, status = os.waitpid(pid, 0)
            exit_code = os.waitstatus_to_exitcode(status)
            break

    if exit_code is None:
        _, status = os.waitpid(pid, 0)
        exit_code = os.waitstatus_to_exitcode(status)

    os.close(fd)
    return exit_code, timed_out, output.decode("utf-8", errors="replace")


def assert_contains(text: str, needle: str) -> None:
    if needle not in text:
        raise AssertionError(f"expected to find {needle!r} in output:\n{text}")


def test_vendorsetup_source_auto_applies_without_prompt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = pathlib.Path(tmp)
        seed_frameworks_base(workspace / "frameworks/base")

        exit_code, timed_out, output = run_source_with_pty(workspace)
        if timed_out:
            raise AssertionError(f"sourcing vendorsetup.sh blocked in PTY:\n{output}")
        if exit_code != 0:
            raise AssertionError(f"sourcing vendorsetup.sh failed with {exit_code}:\n{output}")
        assert_contains(output, "Applied landscape-bootanim.patch.")
        assert_contains(output, "Applied tablet-fwb.patch.")
        if "[y/N]" in output:
            raise AssertionError(f"vendorsetup.sh prompted unexpectedly:\n{output}")


def test_patch_runner_applies_and_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = pathlib.Path(tmp)
        seed_frameworks_base(workspace / "frameworks/base")
        seed_axion_sdk(workspace / "axion_sdk")

        first = run_patch_runner(workspace)
        assert_contains(first.stdout, "Applied landscape-bootanim.patch.")
        assert_contains(first.stdout, "Applied tablet-fwb.patch.")
        assert_contains(first.stdout, "Applied 0001-ax_deviceinfo-use-power-profile-for-battery-capacity.patch.")

        second = run_patch_runner(workspace)
        assert_contains(second.stdout, "Already applied landscape-bootanim.patch.")
        assert_contains(second.stdout, "Already applied tablet-fwb.patch.")
        assert_contains(second.stdout, "Already applied 0001-ax_deviceinfo-use-power-profile-for-battery-capacity.patch.")


def test_patch_runner_fails_on_dirty_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = pathlib.Path(tmp)
        seed_frameworks_base(workspace / "frameworks/base")
        write(
            workspace / "frameworks/base/services/core/java/com/android/server/wm/DisplayRotation.java",
            """
            class DisplayRotation {
                int readDefaultRotation() {
                    return Surface.ROTATION_180;
                }
            }
            """,
        )

        result = run_patch_runner(workspace, check=False)
        if result.returncode == 0:
            raise AssertionError("dirty patch state should fail")
        assert_contains(result.stderr, "is in an unsupported state")


def test_patch_runner_skips_missing_axion_sdk() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = pathlib.Path(tmp)
        seed_frameworks_base(workspace / "frameworks/base")

        result = run_patch_runner(workspace)
        assert_contains(result.stdout, "Skipping optional target")


def test_patch_runner_fails_without_frameworks_base() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = pathlib.Path(tmp)

        result = run_patch_runner(workspace, check=False)
        if result.returncode == 0:
            raise AssertionError("missing frameworks/base should fail")
        assert_contains(result.stderr, "Required target not found")


def main() -> None:
    tests = [
        test_vendorsetup_source_auto_applies_without_prompt,
        test_patch_runner_applies_and_is_idempotent,
        test_patch_runner_fails_on_dirty_state,
        test_patch_runner_skips_missing_axion_sdk,
        test_patch_runner_fails_without_frameworks_base,
    ]
    for test in tests:
        test()


if __name__ == "__main__":
    main()
PY
