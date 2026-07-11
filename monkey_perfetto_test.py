#!/usr/bin/env python3
"""Monkey stress test + Perfetto trace + logcat capture."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    from perfetto.trace_processor import TraceProcessor
    HAS_PERFETTO = True
except ImportError:
    HAS_PERFETTO = False

# ── Logging setup ──────────────────────────────────────────────
log = logging.getLogger("monkey_perfetto")
log.setLevel(logging.DEBUG)
_ch = logging.StreamHandler()
_ch.setFormatter(logging.Formatter("[*] %(message)s"))
_ch.setLevel(logging.INFO)
log.addHandler(_ch)


def _setup_file_logging(out_dir: Path) -> None:
    fh = logging.handlers.RotatingFileHandler(
        str(out_dir / "execution.log"),
        maxBytes=5_000_000,
        backupCount=3,
    )
    fh.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)-5s] %(name)s: %(message)s")
    )
    fh.setLevel(logging.DEBUG)
    log.addHandler(fh)


# ── Helpers ────────────────────────────────────────────────────
def _adb(args: list[str], serial: str = "", timeout: int = 120) -> str:
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += args
    log.debug("$ %s", " ".join(cmd))
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as e:
        log.error("adb timeout: %s", " ".join(cmd))
        raise SystemExit(1) from e
    if r.returncode != 0 and r.stderr:
        stderr = r.stderr.strip()
        if stderr:
            log.warning("adb stderr: %s", stderr)
    return r.stdout


def _adb_shell(
    cmd: str, serial: str = "", timeout: int = 120
) -> str:
    return _adb(["shell", cmd], serial=serial, timeout=timeout)


def _fmt_ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ── Device info collector ─────────────────────────────────────
def _collect_device_info(serial: str) -> dict[str, str]:
    props = {}
    raw = _adb_shell("getprop", serial=serial)
    for line in raw.splitlines():
        m = re.match(r"\[([^\]]+)\]:\s*\[([^\]]*)\]", line)
        if m:
            props[m.group(1)] = m.group(2)
    return props


def _print_device_info(props: dict[str, str]) -> None:
    def g(*keys: str) -> str:
        for k in keys:
            v = props.get(k, "")
            if v:
                return v
        return "?"

    model = g("ro.product.model")
    manu = g("ro.product.manufacturer")
    soc_manu = g("ro.soc.manufacturer")
    soc_model = g("ro.soc.model")
    platform = g("ro.board.platform")
    arch = g("ro.product.cpu.abi")
    serial = g("ro.serialno")

    android = g("ro.build.version.release")
    sdk = g("ro.build.version.sdk")
    sec_patch = g("ro.build.version.security_patch", "ro.vendor.build.security_patch")
    fp = g("ro.build.fingerprint")
    build_type = g("ro.build.type")
    build_tags = g("ro.build.tags")

    rom_ver = g("ro.lunaris.version")
    rom_disp = g("ro.lunaris.display.version")
    maintainer = g("ro.lunaris.maintainer")
    lineage_dev = g("ro.lineage.device")

    boot_state = g("ro.boot.verifiedbootstate")
    vbmeta_dev = g("ro.boot.vbmeta.device_state")
    avb_ver = g("ro.boot.avb_version")
    adb_secure = g("ro.adb.secure")
    debuggable = g("ro.debuggable")

    density = g("ro.sf.lcd_density")
    chars = g("ro.build.characteristics")

    log.info("")
    log.info("=== Device Identity ===")
    log.info("  Model:       %s", model)
    log.info("  Manufacturer: %s", manu)
    log.info("  SoC:         %s %s (%s)", soc_manu, soc_model, platform)
    log.info("  Arch:        %s", arch)
    log.info("  Serial:      %s", serial)

    log.info("")
    log.info("=== Build ===")
    log.info("  Android:     %s (SDK %s)", android, sdk)
    log.info("  Security:    %s", sec_patch)
    log.info("  Fingerprint: %s", fp)
    log.info("  Type:        %s / %s", build_type, build_tags)

    if rom_ver:
        log.info("")
        log.info("=== ROM ===")
        log.info("  ROM:         Lunaris %s (%s)", rom_ver, rom_disp or "?")
        log.info("  Maintainer:  %s", maintainer or "?")
        log.info("  Device:      %s", lineage_dev or "?")

    log.info("")
    log.info("=== Security ===")
    log.info("  Bootloader:  %s / %s", boot_state, vbmeta_dev)
    if avb_ver:
        log.info("  AVB:         %s", avb_ver)
    log.info("  ADB:         %s", "secure" if adb_secure == "1" else "insecure")
    log.info("  Debuggable:  %s", debuggable == "1")

    log.info("")
    log.info("=== Display ===")
    log.info("  Density:     %s dpi", density)
    log.info("  Character:   %s", chars)

    return {
        "model": model,
        "manufacturer": manu,
        "soc": f"{soc_manu} {soc_model}",
        "platform": platform,
        "arch": arch,
        "serial": serial,
        "android": android,
        "sdk": sdk,
        "security_patch": sec_patch,
        "fingerprint": fp,
        "build_type": build_type,
        "build_tags": build_tags,
        "rom_version": rom_ver,
        "rom_display": rom_disp or "",
        "maintainer": maintainer or "",
        "lineage_device": lineage_dev or "",
        "boot_state": boot_state,
        "vbmeta_dev": vbmeta_dev,
        "adb_secure": adb_secure,
        "debuggable": debuggable,
        "density": density,
        "characteristics": chars,
    }


# ── StatsMonitor (background thread) ──────────────────────────
class StatsMonitor(threading.Thread):
    def __init__(self, serial: str, out_file: Path, interval: int = 15) -> None:
        super().__init__(daemon=True)
        self._serial = serial
        self._out_file = out_file
        self._interval = interval
        self._stop = threading.Event()
        self._prev_cpu: list[int] | None = None

    def stop(self) -> None:
        self._stop.set()

    def _parse_cpu(self, raw: str) -> list[int] | None:
        for line in raw.splitlines():
            if line.startswith("cpu "):
                parts = line.split()
                if len(parts) >= 10:
                    return [int(x) for x in parts[1:10]]
        return None

    def _parse_gpu_mem(self) -> str:
        raw = _adb_shell(
            "dumpsys gpu 2>/dev/null",
            serial=self._serial,
            timeout=10,
        )
        global_total = 0
        proc_sum = 0
        for line in raw.splitlines():
            m = re.search(r"Global total:\s*(\d+)", line)
            if m:
                global_total = int(m.group(1))
                continue
            m = re.search(r"Proc \d+ total:\s*(\d+)", line)
            if m:
                proc_sum += int(m.group(1))
        if proc_sum > 0:
            return f"{proc_sum // (1024 * 1024)}M"
        return "?"

    def run(self) -> None:
        log.info("Stats monitor started (every %ss)", self._interval)
        with open(self._out_file, "w") as f:
            while not self._stop.is_set():
                ts = _fmt_ts()
                cpu_raw = _adb_shell(
                    "cat /proc/stat", serial=self._serial, timeout=10
                )
                cur = self._parse_cpu(cpu_raw)
                cpu_pct = "?"
                if cur and self._prev_cpu and len(cur) == len(self._prev_cpu):
                    delta = [cur[i] - self._prev_cpu[i] for i in range(len(cur))]
                    total_delta = sum(delta)
                    idle_delta = delta[3]  # index 3 = idle
                    if total_delta:
                        cpu_pct = f"{100 * (1 - idle_delta / total_delta):.1f}"
                elif cur:
                    cpu_pct = "0.0"  # first sample, no delta yet
                self._prev_cpu = cur

                mem = _adb_shell(
                    "grep MemAvailable /proc/meminfo",
                    serial=self._serial,
                    timeout=10,
                )
                mem_avail = "?"
                for line in mem.splitlines():
                    m = re.search(r"MemAvailable:\s+(\d+)", line)
                    if m:
                        mem_avail = f"{int(m.group(1)) // 1024}"

                batt = _adb_shell(
                    "dumpsys battery 2>/dev/null | grep '^ *level:' | awk '{print $2}'",
                    serial=self._serial,
                    timeout=10,
                )
                batt = batt.strip().splitlines()[0] if batt.strip() else "?"

                gpu = self._parse_gpu_mem()

                fp = _adb_shell(
                    "getprop ro.build.fingerprint",
                    serial=self._serial,
                    timeout=10,
                ).strip()

                short_fp = fp.split("/")[-1] if fp else "?"
                if fp and "/" in fp:
                    parts = fp.split("/")
                    short_fp = parts[-1] if len(parts) <= 2 else f"...{parts[-2]}/{parts[-1]}"
                else:
                    short_fp = fp or "?"
                line = f"[{ts}]  CPU:{cpu_pct}%  MemAvail:{mem_avail}M  GPU:{gpu}  Bat:{batt}%  FP:{short_fp}\n"
                f.write(line)
                f.flush()
                log.debug("stats: %s", line.strip())
                self._stop.wait(self._interval)
        log.info("Stats monitor stopped")


# ── Main orchestrator ─────────────────────────────────────────
class MonkeyPerfettoTest:
    def __init__(self, args: argparse.Namespace) -> None:
        self.monkey_count = args.count
        self.perfetto_duration = args.duration
        self.package = args.package
        self.out_dir = Path(args.out_dir)
        self.run_monkey = not args.no_monkey
        self.run_perfetto = not args.no_perfetto
        self.verbose = args.verbose
        self.serial = ""
        self.props: dict[str, str] = {}
        self.stats_mon: StatsMonitor | None = None
        self.logcat_proc: subprocess.Popen | None = None
        self.perfetto_proc: subprocess.Popen | None = None

    # ── Environment ────────────────────────────────────────────
    def _check_env(self) -> None:
        log.info("Checking environment...")
        try:
            subprocess.run(
                ["adb", "devices"], capture_output=True, timeout=10, check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            log.error("adb not found or not working: %s", exc)
            raise SystemExit(1) from exc

        raw = _adb(["devices"])
        for line in raw.splitlines():
            if "\tdevice" in line:
                self.serial = line.split("\t")[0]
                break
        if not self.serial:
            log.error("No device connected. Run 'adb devices'.")
            raise SystemExit(1)
        log.info("Device: %s", self.serial)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.out_dir = self.out_dir / ts
        self.out_dir.mkdir(parents=True, exist_ok=True)
        _setup_file_logging(self.out_dir)
        log.info("Output: %s", self.out_dir)

    # ── Device info ────────────────────────────────────────────
    def _device_info(self) -> None:
        log.info("Gathering device properties...")
        self.props = _collect_device_info(self.serial)
        _print_device_info(self.props)
        with open(self.out_dir / "device_info.txt", "w") as f:
            for k, v in sorted(self.props.items()):
                f.write(f"{k}={v}\n")
        log.info("Device info → device_info.txt")

    # ── Logcat ─────────────────────────────────────────────────
    def _start_logcat(self) -> None:
        log.info("Clearing logcat buffer...")
        _adb(["logcat", "-c"], serial=self.serial)

        log.info("Starting logcat capture...")
        lf = str(self.out_dir / "logcat.txt")
        self.logcat_proc = subprocess.Popen(
            ["adb", "-s", self.serial, "logcat", "-v", "threadtime", "-b", "all"],
            stdout=open(lf, "w"),
            stderr=subprocess.STDOUT,
        )
        time.sleep(1)
        log.info("Logcat → logcat.txt (PID %s)", self.logcat_proc.pid)

    def _stop_logcat(self) -> None:
        if self.logcat_proc:
            self.logcat_proc.terminate()
            self.logcat_proc.wait(timeout=5)
            self.logcat_proc = None
            log.info("Logcat stopped")

    # ── Perfetto ───────────────────────────────────────────────
    def _gen_perfetto_config(self) -> Path:
        log.info("Preparing Perfetto config...")
        cfg = self.out_dir / "perfetto_config.pbtx"
        dur = self.perfetto_duration * 1000
        cfg.write_text(
            f"""buffers {{
  size_kb: 65536
  fill_policy: RING_BUFFER
}}
buffers {{
  size_kb: 8192
  fill_policy: RING_BUFFER
}}
data_sources {{
  config {{
    name: "linux.ftrace"
    target_buffer: 0
    ftrace_config {{
      ftrace_events: "sched/sched_switch"
      ftrace_events: "sched/sched_wakeup"
      ftrace_events: "sched/sched_wakeup_new"
      ftrace_events: "sched/sched_process_exit"
      ftrace_events: "sched/sched_process_free"
      ftrace_events: "power/cpu_frequency"
      ftrace_events: "power/cpu_idle"
      ftrace_events: "power/suspend_resume"
      ftrace_events: "power/gpu_frequency"
      ftrace_events: "gpu/gpu_mem_total"
    }}
  }}
}}
data_sources {{
  config {{
    name: "linux.process_stats"
    target_buffer: 0
  }}
}}
data_sources {{
  config {{
    name: "linux.sys_stats"
    target_buffer: 0
    sys_stats_config {{
      meminfo_period_ms: 1000
      vmstat_period_ms: 1000
    }}
  }}
}}
data_sources {{
  config {{
    name: "android.power"
    target_buffer: 0
  }}
}}
data_sources {{
  config {{
    name: "android.log"
    target_buffer: 1
    android_log_config {{
      log_ids: LID_DEFAULT
      log_ids: LID_SYSTEM
      log_ids: LID_CRASH
    }}
  }}
}}
data_sources {{
  config {{
    name: "android.surfaceflinger.frame"
    target_buffer: 0
  }}
}}
data_sources {{
  config {{
    name: "track_event"
    target_buffer: 0
  }}
}}
duration_ms: {dur}
write_into_file: true
"""
        )
        log.info("Perfetto config → perfetto_config.pbtx")
        return cfg

    def _run_perfetto(self) -> Path | None:
        if not self.run_perfetto:
            log.info("Skipping Perfetto (--no-perfetto)")
            return None

        cfg = self._gen_perfetto_config()
        remote_cfg = "/data/misc/perfetto-configs/config.pbtx"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        remote_trace = f"/data/misc/perfetto-traces/trace_{ts}.perfetto-trace"
        local_trace = self.out_dir / "trace.perfetto-trace"

        log.info("Pushing config to device...")
        _adb(["push", str(cfg), remote_cfg], serial=self.serial, timeout=15)

        log.info("Starting Perfetto trace (%ss)...", self.perfetto_duration)
        self.perfetto_proc = subprocess.Popen(
            [
                "adb",
                "-s",
                self.serial,
                "shell",
                "perfetto",
                "--txt",
                "-c",
                remote_cfg,
                "-o",
                remote_trace,
            ]
        )
        log.info("Perfetto PID %s", self.perfetto_proc.pid)
        return local_trace

    def _wait_perfetto(self, local_trace: Path) -> Path | None:
        if not self.perfetto_proc:
            return None
        log.info("Waiting for Perfetto to finish...")
        self.perfetto_proc.wait()
        self.perfetto_proc = None
        log.info("Perfetto done, pulling trace...")

        remote_trace = None
        raw = _adb_shell(
            "ls -t /data/misc/perfetto-traces/*.perfetto-trace 2>/dev/null | head -1",
            serial=self.serial,
            timeout=15,
        ).strip()
        if raw:
            remote_trace = raw.splitlines()[0].strip()

        if remote_trace:
            _adb(
                ["pull", remote_trace, str(local_trace)],
                serial=self.serial,
                timeout=120,
            )
            _adb_shell(f"rm -f {remote_trace}", serial=self.serial)

        if local_trace.exists() and local_trace.stat().st_size > 0:
            sz = local_trace.stat().st_size // 1024
            log.info("Perfetto trace → trace.perfetto-trace (%d KB)", sz)
            return local_trace

        log.warning("Perfetto trace not found/empty — data sources may not be supported")
        return None

    # ── Monkey ─────────────────────────────────────────────────
    def _run_monkey(self) -> tuple[str, int, int, int, int, int]:
        if not self.run_monkey:
            log.info("Skipping Monkey (--no-monkey)")
            return "skipped", 0, 0

        log.info("Starting Monkey (%d events)...", self.monkey_count)
        mf = self.out_dir / "monkey_output.txt"

        cmd = "monkey -v -v"
        if self.package:
            cmd += f" -p {self.package}"
        cmd += (
            f" --ignore-crashes --ignore-timeouts"
            f" --ignore-security-exceptions --kill-process-after-error"
            f" {self.monkey_count}"
        )

        start = time.time()
        proc = subprocess.Popen(
            ["adb", "-s", self.serial, "shell", cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        lines: list[str] = []
        for line in proc.stdout:  # type: ignore[union-attr]
            print(line, end="", flush=True)
            lines.append(line)
        proc.wait()
        elapsed = int(time.time() - start)

        output = "".join(lines)
        mf.write_text(output)
        injected = "?"
        for line in lines:
            m = re.search(r"Events injected:\s*(\d+)", line)
            if m:
                injected = m.group(1)
        crashes = sum(1 for line in lines if "// CRASH:" in line)
        anrs = sum(1 for line in lines if "// ANR:" in line)
        secs = sum(1 for line in lines if "// SECURITY:" in line)

        log.info(
            "Monkey finished (exit=%s, %ss) → monkey_output.txt",
            proc.returncode,
            elapsed,
        )
        return injected, crashes, anrs, secs, proc.returncode, elapsed

    # ── Trace analysis ─────────────────────────────────────────
    def _analyze_trace(self, trace_file: Path) -> list[str]:
        if not HAS_PERFETTO:
            log.info("Trace analysis skipped — install: uv pip install perfetto")
            return []
        log.info("Analyzing trace (loading, may take a minute)...")
        try:
            tp = TraceProcessor(file_path=str(trace_file))
        except Exception as e:
            log.warning("Trace analysis failed: %s", e)
            return []

        out: list[str] = []

        qr = tp.query("""
            select t.name, sum(s.dur)/1e9 as cpu_sec, count(*) as slices
            from sched_slice s
            join thread t on s.utid = t.utid
            where t.name is not null and t.name != 'swapper'
            group by s.utid
            order by cpu_sec desc
            limit 8
        """)
        out.append("  Top CPU consumers:")
        for r in qr:
            out.append(f"    {r.name[:30]:<30s} {r.cpu_sec:.1f}s  ({r.slices} slices)")

        out.append(f"  CPU idle (swapper):")
        qr = tp.query("""
            select cpu, sum(dur)/1e9 as idle_sec
            from sched_slice where end_state = 'S'
            group by cpu order by cpu
        """)
        for r in qr:
            total_qr = tp.query("select sum(dur)/1e9 as t from sched_slice where end_state is not null")
            total = next(total_qr).t or 1e-9
            pct = 100 * r.idle_sec / total if total else 0
            out.append(f"    CPU{r.cpu}: {r.idle_sec:.1f}s idle ({pct:.0f}%)")

        qr = tp.query("""
            select t.name as track_name, count(*) as frames, avg(s.dur)/1e6 as avg_ms
            from slice s
            join track t on s.track_id = t.id
            where t.name like 'GPU%'
            group by s.track_id
            having frames > 2
            order by avg_ms desc
            limit 8
        """)
        gpu_rows = list(qr)
        if gpu_rows:
            out.append(f"  GPU frame rendering (slowest apps):")
            for r in gpu_rows:
                name = (r.track_name or "?")[:45]
                out.append(f"    {name:<45s} {r.frames:4d} frames  avg {r.avg_ms:.0f}ms")

        qr = tp.query("""
            select value/1000 as mhz, count(*) as n
            from counter
            where track_id in (select id from track where name = 'cpufreq')
            group by value
            order by mhz desc
            limit 5
        """)
        freq_rows = list(qr)
        if freq_rows:
            min_freq = min(r.mhz for r in freq_rows)
            max_freq = max(r.mhz for r in freq_rows)
            out.append(f"  CPU freq range: {min_freq:.0f}–{max_freq:.0f} MHz")

        qr = tp.query("""
            select max(s.dur)/1e6 as max_ms, t.name as track_name
            from slice s
            join track t on s.track_id = t.id
            where t.name like 'SF%'
            group by s.track_id
            order by max_ms desc
            limit 3
        """)
        sf_rows = list(qr)
        if sf_rows:
            out.append(f"  Max SF pipeline latency:")
            for r in sf_rows:
                name = (r.track_name or "?")[:50]
                out.append(f"    {name:<50s} {r.max_ms:.0f}ms")

        log.info("Trace analysis done (%d lines)", len(out))
        return out

    # ── Summary report ─────────────────────────────────────────
    def _summary(
        self,
        injected: str,
        crashes: int,
        anrs: int,
        secs: int,
        monkey_exit: int,
        monkey_dur: int,
        perfetto_file: Path | None,
        analysis_lines: list[str] | None = None,
    ) -> None:
        log.info("Generating summary...")
        sf = self.out_dir / "summary.txt"

        lcf = self.out_dir / "logcat.txt"
        lc_lines = 0
        lc_fatal = 0
        lc_anr = 0
        if lcf.exists():
            lc_text = lcf.read_text()
            lc_lines = len(lc_text.splitlines())
            lc_fatal = lc_text.count("FATAL")
            lc_anr = lc_text.lower().count("anr")

        lines: list[str] = []
        lines.append("=" * 50)
        lines.append("  Monkey + Perfetto Test Summary")
        lines.append(
            f"  Started:  {datetime.now().strftime('%c')}"
        )
        lines.append(
            f"  Device:   {self.props.get('ro.product.model', '?')}"
        )
        lines.append(
            f"  Android:  {self.props.get('ro.build.version.release', '?')}"
            f" (SDK {self.props.get('ro.build.version.sdk', '?')})"
        )
        lines.append(
            f"  Kernel:   {_adb_shell('uname -r', serial=self.serial).strip()}"
        )
        lines.append("=" * 50)
        lines.append("")
        lines.append("── Monkey ────────────────────────────────────────────")
        lines.append(f"  Events requested: {self.monkey_count}")
        lines.append(f"  Events injected:  {injected}")
        lines.append(f"  Duration:         {monkey_dur}s")
        lines.append(f"  Crashes:          {crashes}")
        lines.append(f"  ANRs:             {anrs}")
        lines.append(f"  Security exc:     {secs}")
        lines.append(f"  Exit code:        {monkey_exit}")
        lines.append("")
        lines.append("── Logcat ────────────────────────────────────────────")
        lines.append(f"  Total lines:  {lc_lines}")
        lines.append(f"  FATAL lines:  {lc_fatal}")
        lines.append(f"  ANR mentions: {lc_anr}")
        lines.append("")
        lines.append("── Perfetto ─────────────────────────────────────────")
        if perfetto_file:
            sz = perfetto_file.stat().st_size // 1024
            lines.append(f"  Trace:       trace.perfetto-trace")
            lines.append(f"  Size:        {sz} KB")
            lines.append(f"  Duration:    {self.perfetto_duration}s configured")
        else:
            lines.append("  (not captured)")
        lines.append("")
        if analysis_lines:
            lines.append("── Trace Analysis ──────────────────────────────────")
            lines.extend(analysis_lines)
            lines.append("")
        stf = self.out_dir / "runtime_stats.txt"
        if stf.exists():
            slines = stf.read_text().splitlines()
            for l in slines[:4]:
                lines.append(f"  {l}")
            if len(slines) > 4:
                lines.append("  ... (runtime_stats.txt)")
            lines.append("")
        lines.append("── Output files ──────────────────────────────────────")
        for f in sorted(self.out_dir.iterdir()):
            sz = f.stat().st_size
            lines.append(f"  {f.name} ({sz:,} bytes)")
        lines.append("")
        lines.append(f"All logs: {self.out_dir}")

        sf.write_text("\n".join(lines) + "\n")
        log.info("Summary → summary.txt")

    # ── Orchestrate ────────────────────────────────────────────
    def run(self) -> None:
        self._check_env()
        self._device_info()
        self._start_logcat()

        # Perfetto
        local_trace = self._run_perfetto()

        # Stats monitor (background)
        stf = self.out_dir / "runtime_stats.txt"
        self.stats_mon = StatsMonitor(self.serial, stf)
        self.stats_mon.start()

        # Monkey (blocks until done)
        injected, crashes, anrs, secs, monkey_exit, monkey_dur = self._run_monkey()

        # Wait for Perfetto
        pt_file = self._wait_perfetto(local_trace) if local_trace else None

        # Stop stats
        if self.stats_mon:
            self.stats_mon.stop()
            self.stats_mon.join(timeout=20)
            self.stats_mon = None
            log.info("Stats monitor stopped")

        # Stop logcat
        self._stop_logcat()

        # Analyze trace (inline, auto)
        al = self._analyze_trace(pt_file) if pt_file and pt_file.exists() else []

        # Summary
        self._summary(injected, crashes, anrs, secs, monkey_exit, monkey_dur, pt_file, al)

        log.info("")
        log.info("All done. Logs in: %s", self.out_dir)


# ── CLI ────────────────────────────────────────────────────────
def main() -> None:
    p = argparse.ArgumentParser(
        description="Monkey stress test + Perfetto trace + logcat capture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-c", "--count", type=int, default=2000, help="Monkey event count")
    p.add_argument(
        "-t", "--duration", type=int, default=60, help="Perfetto trace duration (s)"
    )
    p.add_argument("-p", "--package", help="Target package (default: all)")
    p.add_argument("-o", "--out-dir", default="./logs", help="Output base directory")
    p.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose / debug logging"
    )
    p.add_argument("--no-perfetto", action="store_true", help="Skip Perfetto trace")
    p.add_argument("--no-monkey", action="store_true", help="Skip monkey test")

    args = p.parse_args()
    if args.verbose:
        _ch.setLevel(logging.DEBUG)

    MonkeyPerfettoTest(args).run()


if __name__ == "__main__":
    main()
