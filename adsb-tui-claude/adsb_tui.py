#!/usr/bin/env python3
"""Minimal ADS-B status dashboard for a Raspberry Pi receiver."""

from __future__ import annotations

import curses
import json
import math
import os
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from common import safe_float, summarize_aircraft


REFRESH_SECONDS = 1.0
COLOR_NORMAL = 1
COLOR_WARN = 2
COLOR_ALERT = 3
COLOR_DIM = 4

SDR_MSG_RATE_BASELINE = 24000.0
ADSB_MSG_RATE_BASELINE = 36000.0


class ControllerState(Enum):
    IDLE = "idle"
    INPUT = "input"
    CONFIRMING = "confirming"
    RUNNING = "running"

AIRSPY_STATS_CANDIDATES = (
    "/run/adsb-feeder-airspy/airspy_adsb/stats.json",
    "/run/airspy_adsb/stats.json",
)

READSB_STATS_CANDIDATES = (
    "/run/adsb-feeder-ultrafeeder/readsb/stats.json",
    "/run/readsb/stats.json",
)

READSB_STATUS_CANDIDATES = (
    "/run/adsb-feeder-ultrafeeder/readsb/status.json",
    "/run/readsb/status.json",
)

READSB_RECEIVER_CANDIDATES = (
    "/run/adsb-feeder-ultrafeeder/readsb/receiver.json",
    "/run/readsb/receiver.json",
)

READSB_AIRCRAFT_CANDIDATES = (
    "/run/adsb-feeder-ultrafeeder/readsb/aircraft.json",
    "/run/readsb/aircraft.json",
)

AUTOTUNE_SCRIPT_CANDIDATES = (
    "./autotune.py",
    "/home/pi/adsb-tui/autotune.py",
)

AUTOTUNE_CONFIG_CANDIDATES = (
    "./config.json",
    "/home/pi/adsb-tui/config.json",
)

THERMAL_CANDIDATES = (
    "/sys/class/thermal/thermal_zone0/temp",
    "/sys/class/hwmon/hwmon0/temp1_input",
)

NET_DEV_PATH = "/proc/net/dev"
UPTIME_PATH = "/proc/uptime"
MEMINFO_PATH = "/proc/meminfo"
LOADAVG_PATH = "/proc/loadavg"
CPU_STAT_PATH = "/proc/stat"


class StopDashboard(Exception):
    """Raised when the dashboard should stop cleanly."""


@dataclass
class CpuTimes:
    idle: float
    total: float


@dataclass
class NetworkSnapshot:
    rx_bytes: int
    tx_bytes: int
    timestamp: float


@dataclass
class LoopResult:
    variable: str
    env_key: str
    best_value: str
    baseline_value: str
    score_best: float | None
    score_baseline: float | None


class DashboardState:
    def __init__(self) -> None:
        self.prev_cpu: CpuTimes | None = None
        self.prev_net: NetworkSnapshot | None = None


class AutotuneController:
    def __init__(self) -> None:
        self.script_path = choose_existing(AUTOTUNE_SCRIPT_CANDIDATES)
        self.config_path = choose_existing(AUTOTUNE_CONFIG_CANDIDATES)
        self.state = ControllerState.IDLE
        self.input_buffer = ""
        self.status_level = "dim"
        self.status_text = "idle"
        self.last_command = ""
        self.output_lines = [
            "Commands:",
            "baseline | score | plan [variable]",
            "render KEY=VALUE ...",
            "apply KEY=VALUE ... [live]",
            "gain VALUE [live]",
            "loop [variable] [live]",
            "rollback [live]",
            "Safe start: baseline -> score -> plan -> loop",
        ]
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.confirm_command = ""
        self.confirm_argv: list[str] | None = None
        self.loop_result: LoopResult | None = None
        self._start_time: float | None = None

    @property
    def input_mode(self) -> bool:
        return self.state == ControllerState.INPUT

    @property
    def running(self) -> bool:
        return self.state == ControllerState.RUNNING

    def available(self) -> bool:
        return self.script_path is not None and self.config_path is not None

    def begin_input(self) -> None:
        self.loop_result = None
        self.state = ControllerState.INPUT
        self.input_buffer = ""

    def cancel_input(self) -> None:
        self.state = ControllerState.IDLE
        self.input_buffer = ""

    def awaiting_confirmation(self) -> bool:
        return self.state == ControllerState.CONFIRMING

    def handle_key(self, ch: int) -> None:
        if self.awaiting_confirmation():
            if ch in (27, ord("n"), ord("N")):
                self.confirm_command = ""
                self.confirm_argv = None
                self.state = ControllerState.IDLE
                self._set_status("dim", "live command canceled")
                self.output_lines = [
                    "Live command canceled.",
                    "Nothing was posted to the feeder.",
                    "Press : for command, ? for help",
                ]
                return
            if ch in (ord("y"), ord("Y")):
                command_text = self.confirm_command
                argv = self.confirm_argv
                self.confirm_command = ""
                self.confirm_argv = None
                if command_text and argv:
                    self._execute_command(command_text, argv)
                return
            return
        if ch in (27,):
            self.cancel_input()
            return
        if ch in (curses.KEY_BACKSPACE, 127, 8):
            self.input_buffer = self.input_buffer[:-1]
            return
        if ch in (10, 13):
            command_text = self.input_buffer.strip()
            self.cancel_input()
            if command_text:
                self.start(command_text)
            return
        if 32 <= ch <= 126:
            self.input_buffer += chr(ch)

    def start(self, command_text: str) -> None:
        if self.state == ControllerState.RUNNING:
            self._set_status("warn", "command already running")
            return
        if not self.available():
            self._set_status("alert", "autotune.py or config.json missing")
            return
        try:
            argv, needs_confirm = self._build_command(command_text)
        except ValueError as exc:
            self._set_output(command_text, 1, [str(exc)])
            return
        if needs_confirm:
            self.confirm_command = command_text
            self.confirm_argv = argv
            self.last_command = command_text
            self.state = ControllerState.CONFIRMING
            self._set_status("warn", "confirm live command")
            self.output_lines = [
                f"Confirm live command:",
                command_text,
                "Press y to continue.",
                "Press n or Esc to cancel.",
            ]
            return
        self._execute_command(command_text, argv)

    def _set_status(self, level: str, text: str) -> None:
        with self._lock:
            self.status_level = level
            self.status_text = text

    def _set_output(self, command_text: str, returncode: int, output: list[str]) -> None:
        level = "normal" if returncode == 0 else "alert"
        status = f"ok ({returncode})" if returncode == 0 else f"error ({returncode})"
        trimmed = output[-10:]
        loop_result: LoopResult | None = None
        if returncode == 0:
            for line in output:
                if line.startswith("LOOP_RESULT:"):
                    try:
                        data = json.loads(line[len("LOOP_RESULT:"):])
                        loop_result = LoopResult(
                            variable=data["variable"],
                            env_key=data["env_key"],
                            best_value=data["best"],
                            baseline_value=data["baseline"],
                            score_best=data.get("score_best"),
                            score_baseline=data.get("score_baseline"),
                        )
                    except Exception:
                        pass
                    break
        with self._lock:
            self.status_level = level
            self.status_text = status
            self.last_command = command_text
            self.output_lines = trimmed
            self._start_time = None
            if loop_result is not None:
                self.loop_result = loop_result

    def confirm_loop_result(self, keep: bool) -> None:
        if self.loop_result is None:
            return
        if keep:
            self.loop_result = None
            self._set_status("normal", "setting kept")
        else:
            baseline = self.loop_result.baseline_value
            self.loop_result = None
            python_exec = sys.executable or shutil.which("python3") or "python3"
            argv = self._script_argv(python_exec, "rollback-last")
            self._execute_command(f"rollback to {baseline} (auto)", argv)

    def _execute_command(self, command_text: str, argv: list[str]) -> None:
        self.loop_result = None
        self.state = ControllerState.RUNNING
        self.last_command = command_text
        self._start_time = time.time()
        self._set_status("warn", "running")

        def worker() -> None:
            try:
                process = subprocess.Popen(
                    argv,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(self.script_path.parent if self.script_path else Path.cwd()),
                    env=os.environ.copy(),
                )
                all_lines: list[str] = []
                assert process.stdout is not None
                for raw_line in process.stdout:
                    line = raw_line.rstrip("\n")
                    all_lines.append(line)
                    with self._lock:
                        self.output_lines = all_lines[-10:]
                process.wait()
                output = all_lines or ["(no output)"]
                self._set_output(command_text, process.returncode, output)
            except Exception as exc:  # pragma: no cover - defensive for runtime on Pi
                self._set_output(command_text, 1, [f"Command failed: {exc}"])
            finally:
                self.state = ControllerState.IDLE

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def _script_argv(self, python_exec: str, subcommand: str, *extra: str) -> list[str]:
        return [python_exec, str(self.script_path), subcommand, "--config", str(self.config_path), *extra]

    def _build_command(self, command_text: str) -> tuple[list[str], bool]:
        tokens = shlex.split(command_text)
        if not tokens:
            raise ValueError("Empty command")

        command = tokens[0].lower()
        extras = tokens[1:]
        python_exec = sys.executable or shutil.which("python3") or "python3"

        if command == "baseline":
            return self._script_argv(python_exec, "baseline"), False
        if command == "score":
            return self._script_argv(python_exec, "score"), False
        if command == "plan":
            argv = self._script_argv(python_exec, "plan-gain-sweep")
            if extras:
                argv.extend(["--variable", extras[0]])
            return argv, False
        if command == "render":
            if not extras:
                raise ValueError("Usage: render KEY=VALUE ...")
            argv = self._script_argv(python_exec, "render-extra-env")
            for item in extras:
                argv.extend(["--set", item])
            return argv, False
        if command == "apply":
            if not extras:
                raise ValueError("Usage: apply KEY=VALUE ... [live]")
            live = False
            argv = self._script_argv(python_exec, "apply-extra-env")
            for item in extras:
                if item.lower() == "live":
                    live = True
                else:
                    argv.extend(["--set", item])
            if not live:
                argv.append("--dry-run")
            return argv, live
        if command == "gain":
            if not extras:
                raise ValueError("Usage: gain VALUE [live]")
            live = len(extras) > 1 and extras[1].lower() == "live"
            argv = self._script_argv(python_exec, "apply-gain", "--gain", extras[0])
            if not live:
                argv.append("--dry-run")
            return argv, live
        if command == "rollback":
            live = bool(extras and extras[0].lower() == "live")
            argv = self._script_argv(python_exec, "rollback-last")
            if not live:
                argv.append("--dry-run")
            return argv, live
        if command == "loop":
            live = False
            variable_name = ""
            for item in extras:
                if item.lower() == "live":
                    live = True
                elif not variable_name:
                    variable_name = item
                else:
                    raise ValueError("Usage: loop [variable] [live]")
            argv = self._script_argv(python_exec, "auto-gain-loop")
            if variable_name:
                argv.extend(["--variable", variable_name])
            if not live:
                argv.append("--dry-run")
            return argv, live
        raise ValueError(
            "Unknown command. Try: baseline, score, plan, render, apply, gain, loop, rollback"
        )


def choose_existing(candidates: tuple[str, ...]) -> Path | None:
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path
    return None


def read_json(candidates: tuple[str, ...]) -> tuple[dict[str, Any], Path | None]:
    path = choose_existing(candidates)
    if path is None:
        return {}, None

    try:
        return json.loads(path.read_text(encoding="utf-8")), path
    except (OSError, json.JSONDecodeError):
        return {}, path


def read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def format_bytes(num: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def format_rate(num: float) -> str:
    return f"{format_bytes(num)}/s"


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_cpu_times() -> CpuTimes | None:
    raw = read_text(CPU_STAT_PATH)
    if not raw:
        return None
    first = raw.splitlines()[0].split()
    if len(first) < 8 or first[0] != "cpu":
        return None
    values = [float(value) for value in first[1:]]
    idle = values[3] + values[4]
    total = sum(values)
    return CpuTimes(idle=idle, total=total)


def get_cpu_percent(state: DashboardState) -> float | None:
    current = parse_cpu_times()
    if current is None:
        return None

    previous = state.prev_cpu
    state.prev_cpu = current
    if previous is None:
        return None

    total_delta = current.total - previous.total
    idle_delta = current.idle - previous.idle
    if total_delta <= 0:
        return None
    return max(0.0, min(100.0, 100.0 * (1.0 - idle_delta / total_delta)))


def get_loadavg() -> tuple[float, float, float] | None:
    raw = read_text(LOADAVG_PATH)
    if not raw:
        return None
    parts = raw.split()
    if len(parts) < 3:
        return None
    return float(parts[0]), float(parts[1]), float(parts[2])


def get_meminfo() -> tuple[int, int] | None:
    raw = read_text(MEMINFO_PATH)
    if not raw:
        return None

    data: dict[str, int] = {}
    for line in raw.splitlines():
        key, _, value = line.partition(":")
        fields = value.strip().split()
        if fields:
            data[key] = int(fields[0]) * 1024

    total = data.get("MemTotal")
    available = data.get("MemAvailable")
    if total is None or available is None:
        return None
    used = total - available
    return used, total


def get_disk_usage(path: str = "/") -> tuple[int, int] | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    return usage.used, usage.total


def get_temperature_c() -> float | None:
    for candidate in THERMAL_CANDIDATES:
        raw = read_text(candidate)
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if value > 1000:
            value /= 1000.0
        return value
    return None


def get_uptime_seconds() -> float | None:
    raw = read_text(UPTIME_PATH)
    if not raw:
        return None
    try:
        return float(raw.split()[0])
    except (IndexError, ValueError):
        return None


def get_network_rate(state: DashboardState) -> tuple[float, float] | None:
    raw = read_text(NET_DEV_PATH)
    if not raw:
        return None

    rx_total = 0
    tx_total = 0
    for line in raw.splitlines()[2:]:
        if ":" not in line:
            continue
        iface, values = line.split(":", 1)
        iface = iface.strip()
        if iface == "lo":
            continue
        fields = values.split()
        if len(fields) < 16:
            continue
        rx_total += int(fields[0])
        tx_total += int(fields[8])

    snapshot = NetworkSnapshot(rx_total, tx_total, time.time())
    previous = state.prev_net
    state.prev_net = snapshot
    if previous is None:
        return None

    elapsed = snapshot.timestamp - previous.timestamp
    if elapsed <= 0:
        return None
    return (
        max(0.0, (snapshot.rx_bytes - previous.rx_bytes) / elapsed),
        max(0.0, (snapshot.tx_bytes - previous.tx_bytes) / elapsed),
    )


def percent_bar(width: int, percent: float | None) -> str:
    if width < 3:
        return ""
    if percent is None:
        return "[" + ("?" * (width - 2)) + "]"
    inner = width - 2
    filled = max(0, min(inner, math.floor(inner * percent / 100.0)))
    return "[" + ("#" * filled) + ("." * (inner - filled)) + "]"


def init_colors() -> None:
    if not curses.has_colors():
        return
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(COLOR_NORMAL, curses.COLOR_GREEN, -1)
    curses.init_pair(COLOR_WARN, curses.COLOR_YELLOW, -1)
    curses.init_pair(COLOR_ALERT, curses.COLOR_RED, -1)
    curses.init_pair(COLOR_DIM, curses.COLOR_CYAN, -1)


def color_attr(level: str) -> int:
    if not curses.has_colors():
        return curses.A_NORMAL
    mapping = {
        "normal": curses.color_pair(COLOR_NORMAL),
        "warn": curses.color_pair(COLOR_WARN),
        "alert": curses.color_pair(COLOR_ALERT),
        "dim": curses.color_pair(COLOR_DIM),
    }
    return mapping.get(level, curses.A_NORMAL)


def metric_level(value: float | None, warn_at: float, alert_at: float) -> str:
    if value is None:
        return "dim"
    if value >= alert_at:
        return "alert"
    if value >= warn_at:
        return "warn"
    return "normal"


def inverse_metric_level(value: float | None, warn_below: float, alert_below: float) -> str:
    if value is None:
        return "dim"
    if value <= alert_below:
        return "alert"
    if value <= warn_below:
        return "warn"
    return "normal"


def build_pi_lines(
    width: int,
    cpu_percent: float | None,
    loadavg: tuple[float, float, float] | None,
    meminfo: tuple[int, int] | None,
    disk: tuple[int, int] | None,
    temp_c: float | None,
    uptime: float | None,
    network: tuple[float, float] | None,
) -> list[str]:

    lines = ["Pi"]
    lines.append(
        f"CPU  : {cpu_percent:5.1f}%" if cpu_percent is not None else "CPU  : unavailable"
    )
    lines.append(percent_bar(width - 2, cpu_percent))
    if loadavg is not None:
        lines.append(f"Load : {loadavg[0]:.2f}  {loadavg[1]:.2f}  {loadavg[2]:.2f}")
    if temp_c is not None:
        lines.append(f"Temp : {temp_c:.1f} C")
    if meminfo is not None:
        used, total = meminfo
        lines.append(f"Mem  : {format_bytes(used)} / {format_bytes(total)}")
    if disk is not None:
        used, total = disk
        lines.append(f"Disk : {format_bytes(used)} / {format_bytes(total)}")
    if uptime is not None:
        lines.append(f"Up   : {format_duration(uptime)}")
    if network is not None:
        rx, tx = network
        lines.append(f"Net  : down {format_rate(rx)}  up {format_rate(tx)}")
    return lines


def build_sdr_lines(airspy_stats: dict[str, Any], path: Path | None, width: int) -> list[str]:
    lines = ["SDR"]
    if not airspy_stats:
        lines.append("No Airspy stats JSON found")
        if path is not None:
            lines.append(str(path))
        return lines

    gain = safe_float(airspy_stats.get("gain"))
    samplerate = safe_float(airspy_stats.get("samplerate"))
    lost_buffers = airspy_stats.get("lost_buffers")
    max_aircraft = airspy_stats.get("max_aircraft_count")
    rssi = airspy_stats.get("rssi", {})
    snr = airspy_stats.get("snr", {})
    noise = airspy_stats.get("noise", {})
    df_counts = airspy_stats.get("df_counts", [])

    messages = sum(value for value in df_counts if isinstance(value, int))
    lines.append(f"Path : {path}" if path is not None else "Path : unavailable")
    if gain is not None:
        lines.append(f"Gain : {gain:.1f} dB")
    if samplerate is not None:
        lines.append(f"Rate : {samplerate:.1f} MSPS")
    lines.append(f"Msgs : {messages / 60.0:.1f}/s (last minute)")
    if isinstance(max_aircraft, int):
        lines.append(f"Peak : {max_aircraft} aircraft/min")
    if isinstance(lost_buffers, int):
        lines.append(f"Loss : {lost_buffers} buffers")
    if isinstance(rssi, dict):
        median = safe_float(rssi.get("median"))
        p95 = safe_float(rssi.get("p95"))
        if median is not None and p95 is not None:
            lines.append(f"RSSI : med {median:.1f}  p95 {p95:.1f}")
    if isinstance(snr, dict):
        median = safe_float(snr.get("median"))
        p95 = safe_float(snr.get("p95"))
        if median is not None and p95 is not None:
            lines.append(f"SNR  : med {median:.1f}  p95 {p95:.1f}")
    if isinstance(noise, dict):
        median = safe_float(noise.get("median"))
        if median is not None:
            lines.append(f"Noise: median {median:.1f}")

    preamble = safe_float(airspy_stats.get("preamble_filter"))
    if preamble is not None:
        lines.append(f"Filter: {preamble:.0f}")

    lines.append(percent_bar(width - 2, min(100.0, (messages / SDR_MSG_RATE_BASELINE) * 100.0)))
    return lines


def build_adsb_lines(
    stats: dict[str, Any],
    status: dict[str, Any],
    receiver: dict[str, Any],
    aircraft_json: dict[str, Any],
    width: int,
) -> list[str]:
    lines = ["ADS-B"]
    if not stats:
        lines.append("No readsb stats JSON found")
        return lines

    last1 = stats.get("last1min", {})
    last5 = stats.get("last5min", {})
    summary = summarize_aircraft(aircraft_json)

    count_total = summary["total"] or (
        int(status.get("aircraft_with_pos", 0)) + int(status.get("aircraft_without_pos", 0))
    )
    count_pos = summary["with_pos"] or int(status.get("aircraft_with_pos", 0))
    count_no_pos = max(0, count_total - count_pos)

    messages_1m = safe_float(last1.get("messages"))
    pos_1m = safe_float(last1.get("position_count_total"))
    messages_5m = safe_float(last5.get("messages"))
    distance_m = safe_float(last1.get("max_distance")) or safe_float(last5.get("max_distance"))
    cpr = last1.get("cpr", {})
    remote = last1.get("remote", {})

    lines.append(f"Aircraft : {count_total} total  {count_pos} with pos  {count_no_pos} no pos")
    if messages_1m is not None:
        lines.append(f"Msgs     : {messages_1m / 60.0:.1f}/s  ({int(messages_1m):,} last min)")
    if pos_1m is not None:
        lines.append(f"Positions: {pos_1m / 60.0:.1f}/s  ({int(pos_1m):,} last min)")
    if messages_5m is not None:
        lines.append(f"5m Avg   : {messages_5m / 300.0:.1f}/s")
    if distance_m is not None:
        lines.append(f"Range    : {distance_m / 1852.0:.1f} nmi max")
    if isinstance(cpr, dict):
        global_ok = int(cpr.get("global_ok", 0))
        local_ok = int(cpr.get("local_ok", 0))
        lines.append(f"CPR Fixes: global {global_ok}  local {local_ok}")
    if isinstance(remote, dict):
        bytes_in = safe_float(remote.get("bytes_in"))
        bytes_out = safe_float(remote.get("bytes_out"))
        if bytes_in is not None and bytes_out is not None:
            lines.append(
                f"Feeds    : in {format_bytes(bytes_in / 60.0)}/s  out {format_bytes(bytes_out / 60.0)}/s"
            )

    closest = summary["closest_nm"]
    farthest = summary["farthest_nm"]
    if closest is not None and farthest is not None:
        lines.append(f"Live Dist: closest {closest:.1f} nmi  farthest {farthest:.1f} nmi")
    strongest = summary["strongest_rssi"]
    if strongest is not None:
        lines.append(f"Live RF  : strongest {strongest:.1f} dBFS  hot targets {summary['strong_count']}")
    if summary["grounded"]:
        lines.append(f"Low Alt  : {summary['grounded']} targets <= 1500 ft")

    version = receiver.get("version")
    if isinstance(version, str):
        lines.append(f"Build    : {version[: max(0, width - 11)]}")

    if messages_1m is not None:
        lines.append(percent_bar(width - 2, min(100.0, (messages_1m / ADSB_MSG_RATE_BASELINE) * 100.0)))
    return lines


def build_footer(
    airspy_path: Path | None, readsb_path: Path | None, status_path: Path | None
) -> str:
    parts = ["q: quit", "?: help", ":: autotune cmd"]
    if airspy_path is not None:
        parts.append(f"sdr={airspy_path}")
    if readsb_path is not None:
        parts.append(f"stats={readsb_path}")
    if status_path is not None:
        parts.append(f"status={status_path}")
    return " | ".join(parts)


def draw_box(
    stdscr: curses.window, y: int, x: int, h: int, w: int, lines: list[str], levels: list[str] | None = None
) -> None:
    if h < 3 or w < 4:
        return
    stdscr.addstr(y, x, "+" + "-" * (w - 2) + "+")
    for row in range(1, h - 1):
        stdscr.addstr(y + row, x, "|" + " " * (w - 2) + "|")
    stdscr.addstr(y + h - 1, x, "+" + "-" * (w - 2) + "+")

    for index, line in enumerate(lines[: h - 2]):
        text = line[: w - 4]
        level = levels[index] if levels and index < len(levels) else "dim" if index == 0 else "normal"
        attr = curses.A_BOLD if index == 0 else color_attr(level)
        stdscr.addstr(y + 1 + index, x + 2, text, attr)


def build_autotune_lines(width: int, controller: AutotuneController) -> tuple[list[str], list[str]]:
    if controller.loop_result is not None and controller.state == ControllerState.IDLE:
        r = controller.loop_result
        delta_str = ""
        if r.score_best is not None and r.score_baseline is not None:
            delta = r.score_best - r.score_baseline
            delta_str = f"  score {r.score_baseline:.1f}→{r.score_best:.1f} ({delta:+.1f})"
        lines = [
            "Loop complete",
            f"{r.env_key}: {r.baseline_value} → {r.best_value}{delta_str}",
            "",
            "y = keep this setting",
            "n / Esc = rollback to previous",
        ]
        levels = ["dim", "normal", "normal", "warn", "warn"]
        lines.extend(controller.output_lines[-5:])
        levels.extend(["dim"] * len(controller.output_lines[-5:]))
        return lines, levels

    lines = ["Autotune"]
    levels = ["dim"]

    if controller.script_path is None:
        lines.append("Script : autotune.py not found")
        levels.append("alert")
    else:
        lines.append(f"Script : {controller.script_path}")
        levels.append("dim")

    if controller.config_path is None:
        lines.append("Config : config.json not found")
        levels.append("alert")
    else:
        lines.append(f"Config : {controller.config_path}")
        levels.append("dim")

    status_text = f"Status : {controller.status_text}"
    if controller.running:
        if controller._start_time is not None:
            elapsed = int(time.time() - controller._start_time)
            m, s = divmod(elapsed, 60)
            status_text += f" ({m}m{s:02d}s)"
        else:
            status_text += " ..."
    lines.append(status_text)
    levels.append(controller.status_level)

    if controller.last_command:
        lines.append(f"Last   : {controller.last_command}")
        levels.append("normal")
    else:
        lines.append("Last   : none")
        levels.append("dim")

    if controller.input_mode:
        prompt = f"> {controller.input_buffer}"
    elif controller.awaiting_confirmation():
        prompt = "Live confirm: press y to run, n/Esc to cancel"
    else:
        prompt = "Press : for command, ? for help"
    lines.append(prompt[: max(0, width - 4)])
    levels.append("warn" if controller.input_mode or controller.awaiting_confirmation() else "dim")

    lines.extend(controller.output_lines)
    levels.extend(["normal"] * len(controller.output_lines))
    return lines, levels


def build_help_lines() -> list[str]:
    return [
        "ADS-B TUI Help",
        "",
        "Safest sequence:",
        "1. baseline",
        "2. score",
        "3. plan",
        "4. loop",
        "5. loop live only after dry-run looks right",
        "",
        "Mini commands:",
        "baseline            save current baseline snapshot",
        "score               score current station state",
        "plan [variable]     show candidate plan only",
        "render KEY=VALUE    preview full env block",
        "apply KEY=VALUE     preview manual change",
        "apply ... live      post manual change and restart",
        "gain VALUE          preview gain change",
        "gain VALUE live     apply one gain immediately",
        "loop [variable]     dry-run automated loop",
        "loop ... live       live automated loop",
        "rollback            preview rollback",
        "rollback live       restore previous env block",
        "",
        "Rules:",
        "- do not start with live",
        "- every live command asks for y/n confirmation",
        "- change one variable family at a time",
        "- start with gain, then timeout, then cputime_target",
        "- use rollback live if a result looks wrong",
        "",
        "Keys: q quit | : command | ? toggle help | y/n live confirm | Esc close input/help",
    ]


def draw_overlay(stdscr: curses.window, lines: list[str]) -> None:
    height, width = stdscr.getmaxyx()
    box_width = min(width - 4, 90)
    box_height = min(height - 4, max(10, len(lines) + 2))
    start_y = max(1, (height - box_height) // 2)
    start_x = max(2, (width - box_width) // 2)
    trimmed_lines = [line[: max(0, box_width - 4)] for line in lines[: max(0, box_height - 2)]]
    levels = ["dim"] + ["normal"] * (len(trimmed_lines) - 1)
    draw_box(stdscr, start_y, start_x, box_height, box_width, trimmed_lines, levels)


def build_header_status(
    cpu_percent: float | None,
    temp_c: float | None,
    airspy_stats: dict[str, Any],
    readsb_stats: dict[str, Any],
    aircraft_json: dict[str, Any],
) -> tuple[str, str]:
    airspy_messages = 0
    df_counts = airspy_stats.get("df_counts", [])
    if isinstance(df_counts, list):
        airspy_messages = sum(value for value in df_counts if isinstance(value, int))

    last1 = readsb_stats.get("last1min", {})
    adsb_rate = safe_float(last1.get("messages"))
    aircraft = summarize_aircraft(aircraft_json)

    left = (
        f"CPU {cpu_percent:4.1f}%"
        if cpu_percent is not None
        else "CPU --.-%"
    )
    if temp_c is not None:
        left += f" | Temp {temp_c:4.1f}C"
    left += f" | SDR {airspy_messages / 60.0:4.1f} msg/s"

    right = (
        f"ADS-B {adsb_rate / 60.0:4.1f} msg/s"
        if adsb_rate is not None
        else "ADS-B --.- msg/s"
    )
    right += f" | Aircraft {aircraft['total']}"
    return left, right


@dataclass
class FrameMetrics:
    airspy_stats: dict[str, Any]
    airspy_path: Path | None
    readsb_stats: dict[str, Any]
    readsb_path: Path | None
    readsb_status: dict[str, Any]
    status_path: Path | None
    readsb_receiver: dict[str, Any]
    readsb_aircraft: dict[str, Any]
    cpu_percent: float | None
    temp_c: float | None
    loadavg: tuple[float, float, float] | None
    meminfo: tuple[int, int] | None
    disk: tuple[int, int] | None
    uptime: float | None
    network: tuple[float, float] | None


def _handle_input(ch: int, autotune: AutotuneController, help_visible: bool) -> bool:
    """Process one keypress; return updated help_visible. Raises StopDashboard on quit."""
    if autotune.loop_result is not None and autotune.state == ControllerState.IDLE:
        if ch in (ord("y"), ord("Y"), 10, 13):
            autotune.confirm_loop_result(keep=True)
            return help_visible
        if ch in (ord("n"), ord("N"), 27):
            autotune.confirm_loop_result(keep=False)
            return help_visible
        # other keys (q, :, ?) fall through to normal handling below
    if autotune.awaiting_confirmation():
        autotune.handle_key(ch)
    elif autotune.input_mode:
        autotune.handle_key(ch)
    elif help_visible:
        if ch in (27, ord("?"), ord("q"), ord("Q")):
            return False
    elif ch in (ord("q"), ord("Q")):
        raise StopDashboard
    elif ch == ord(":"):
        autotune.begin_input()
    elif ch == ord("?"):
        return True
    return help_visible


def _collect_metrics(state: DashboardState) -> FrameMetrics:
    airspy_stats, airspy_path = read_json(AIRSPY_STATS_CANDIDATES)
    readsb_stats, readsb_path = read_json(READSB_STATS_CANDIDATES)
    readsb_status, status_path = read_json(READSB_STATUS_CANDIDATES)
    readsb_receiver, _receiver_path = read_json(READSB_RECEIVER_CANDIDATES)
    readsb_aircraft, _aircraft_path = read_json(READSB_AIRCRAFT_CANDIDATES)
    return FrameMetrics(
        airspy_stats=airspy_stats,
        airspy_path=airspy_path,
        readsb_stats=readsb_stats,
        readsb_path=readsb_path,
        readsb_status=readsb_status,
        status_path=status_path,
        readsb_receiver=readsb_receiver,
        readsb_aircraft=readsb_aircraft,
        cpu_percent=get_cpu_percent(state),
        temp_c=get_temperature_c(),
        loadavg=get_loadavg(),
        meminfo=get_meminfo(),
        disk=get_disk_usage("/"),
        uptime=get_uptime_seconds(),
        network=get_network_rate(state),
    )


def _render_frame(
    stdscr: curses.window, m: FrameMetrics, autotune: AutotuneController, help_visible: bool
) -> None:
    height, width = stdscr.getmaxyx()
    stdscr.erase()

    header_left, header_right = build_header_status(
        m.cpu_percent, m.temp_c, m.airspy_stats, m.readsb_stats, m.readsb_aircraft
    )
    title = "Raspberry Pi ADS-B Dashboard"
    subtitle = time.strftime("%Y-%m-%d %H:%M:%S")
    stdscr.addstr(0, 2, title[: max(0, width - 4)])
    stdscr.addstr(1, 2, header_left[: max(0, width - 4)], color_attr(metric_level(m.cpu_percent, 60, 85)))
    right_x = max(2, width - len(header_right) - 2)
    if right_x > len(header_left) + 5:
        stdscr.addstr(1, right_x, header_right[: max(0, width - right_x - 1)], color_attr("dim"))
    stdscr.addstr(2, 2, subtitle[: max(0, width - 4)], color_attr("dim"))

    panel_top = 4
    footer_rows = 2
    panel_height = max(8, height - panel_top - footer_rows)

    autotune_lines, autotune_levels = build_autotune_lines(width, autotune)

    if width >= 120:
        gap = 1
        left_width = max(28, (width - gap) // 4)
        right_x = left_width + gap
        right_width = max(30, width - right_x)
        left_height = max(7, panel_height // 2)
        lower_y = panel_top + left_height
        lower_height = max(5, panel_height - left_height)
        adsb_height = max(8, panel_height // 2)
        autotune_y = panel_top + adsb_height
        autotune_height = max(6, panel_height - adsb_height)
        boxes = [
            (
                panel_top,
                0,
                left_height,
                left_width,
                build_pi_lines(left_width, m.cpu_percent, m.loadavg, m.meminfo, m.disk, m.temp_c, m.uptime, m.network),
            ),
            (
                lower_y,
                0,
                lower_height,
                left_width,
                build_sdr_lines(m.airspy_stats, m.airspy_path, left_width),
            ),
            (
                panel_top,
                right_x,
                adsb_height,
                right_width,
                build_adsb_lines(m.readsb_stats, m.readsb_status, m.readsb_receiver, m.readsb_aircraft, right_width),
            ),
            (
                autotune_y,
                right_x,
                autotune_height,
                right_width,
                autotune_lines,
                autotune_levels,
            ),
        ]
    else:
        single_height = max(6, (panel_height - 3) // 4)
        boxes = [
            (panel_top, 0, single_height, width, build_pi_lines(width, m.cpu_percent, m.loadavg, m.meminfo, m.disk, m.temp_c, m.uptime, m.network)),
            (
                panel_top + single_height,
                0,
                single_height,
                width,
                build_sdr_lines(m.airspy_stats, m.airspy_path, width),
            ),
            (
                panel_top + 2 * single_height,
                0,
                single_height,
                width,
                build_adsb_lines(m.readsb_stats, m.readsb_status, m.readsb_receiver, m.readsb_aircraft, width),
            ),
            (
                panel_top + 3 * single_height,
                0,
                height - (panel_top + 3 * single_height) - footer_rows,
                width,
                autotune_lines,
                autotune_levels,
            ),
        ]

    for box in boxes:
        if len(box) == 5:
            y, x, h, w, lines = box
            levels = None
        else:
            y, x, h, w, lines, levels = box
        if h > 2 and w > 4:
            if levels is None:
                levels = ["dim"] * len(lines)
            if lines and lines[0] == "Pi":
                levels = [
                    "dim",
                    metric_level(m.cpu_percent, 60, 85),
                    metric_level(m.cpu_percent, 60, 85),
                    metric_level(m.loadavg[0] if m.loadavg else None, 3.0, 6.0),
                    metric_level(m.temp_c, 65, 78),
                    "normal",
                    "normal",
                    "normal",
                ]
            elif lines and lines[0] == "SDR":
                sdr_rssi = safe_float(m.airspy_stats.get("rssi", {}).get("median"))
                sdr_snr = safe_float(m.airspy_stats.get("snr", {}).get("median"))
                lost_buffers = safe_float(m.airspy_stats.get("lost_buffers"))
                levels = [
                    "dim",
                    "dim",
                    "normal",
                    "normal",
                    "normal",
                    "normal",
                    metric_level(lost_buffers, 1, 3),
                    inverse_metric_level(sdr_rssi, 35, 32),
                    inverse_metric_level(sdr_snr, 10, 7),
                    "normal",
                    "normal",
                    "normal",
                ]
            elif lines and lines[0] == "ADS-B":
                last1 = m.readsb_stats.get("last1min", {})
                last5 = m.readsb_stats.get("last5min", {})
                msg_rate = safe_float(last1.get("messages"))
                msg_rate_5m = safe_float(last5.get("messages"))
                max_range_nm = safe_float(last1.get("max_distance"))
                if max_range_nm is not None:
                    max_range_nm /= 1852.0
                levels = [
                    "dim",
                    "normal",
                    inverse_metric_level(msg_rate / 60.0 if msg_rate is not None else None, 250, 120),
                    "normal",
                    inverse_metric_level(msg_rate_5m / 300.0 if msg_rate_5m is not None else None, 250, 120),
                    inverse_metric_level(max_range_nm, 120, 60),
                    "normal",
                    "normal",
                    "normal",
                    "normal",
                    "normal",
                    "dim",
                    "normal",
                ]
            draw_box(stdscr, y, x, h, w, lines, levels)

    footer = build_footer(m.airspy_path, m.readsb_path, m.status_path)
    stdscr.addstr(max(0, height - 2), 0, footer[: max(0, width - 1)])
    if help_visible:
        draw_overlay(stdscr, build_help_lines())
    stdscr.refresh()


def run_dashboard(stdscr: curses.window) -> None:
    curses.curs_set(0)
    init_colors()
    stdscr.nodelay(True)
    stdscr.timeout(int(REFRESH_SECONDS * 1000))

    state = DashboardState()
    autotune = AutotuneController()
    help_visible = False

    while True:
        ch = stdscr.getch()
        help_visible = _handle_input(ch, autotune, help_visible)
        metrics = _collect_metrics(state)
        _render_frame(stdscr, metrics, autotune, help_visible)


def main() -> int:
    signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        curses.wrapper(run_dashboard)
    except (KeyboardInterrupt, StopDashboard):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
