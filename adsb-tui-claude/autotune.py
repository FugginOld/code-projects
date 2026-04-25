#!/usr/bin/env python3
"""ADS-B autotune toolkit for Airspy/readsb setups."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import time

from common import safe_float, summarize_aircraft

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _validate_config(config: dict[str, Any], path: Path) -> None:
    missing = []
    if not isinstance(config.get("output"), dict) or "state_dir" not in config["output"]:
        missing.append("output.state_dir")
    if not isinstance(config.get("scoring"), dict) or "weights" not in config["scoring"]:
        missing.append("scoring.weights")
    if missing:
        raise ValueError(f"Config {path} is missing required keys: {', '.join(missing)}")


def read_config(path: Path) -> dict[str, Any]:
    config = load_json(path)
    _validate_config(config, path)
    state_dir = Path(config["output"]["state_dir"])
    if not state_dir.is_absolute():
        state_dir = (path.parent / state_dir).resolve()
    config["output"]["state_dir"] = str(state_dir)
    controller = config.setdefault("controller", {})
    controller.setdefault("base_url", "http://192.168.9.74")
    controller.setdefault("expert_path", "/expert")
    controller.setdefault("restart_path", "/restart")
    controller.setdefault("restart_timeout_seconds", 180)
    controller.setdefault("restart_poll_seconds", 1.0)
    controller.setdefault("settle_seconds", 10)
    tuning = config.setdefault("tuning", {})
    tuning.setdefault("env_field", "ultrafeeder_extra_env")
    tuning.setdefault("submit_field", "ultrafeeder_extra_env--submit")
    tuning.setdefault("submit_value", "go")
    tuning.setdefault("gain_env_key", "AIRSPY_ADSB_GAIN")
    tuning.setdefault("sample_interval_seconds", 30)
    tuning.setdefault("significant_improvement", tuning.get("minimum_improvement", 0.0))
    tuning.setdefault("marginal_range_gain_nm", 0.0)
    tuning.setdefault("max_aircraft_with_pos_drop", 0.0)
    tuning.setdefault("max_messages_per_second_drop", 0.0)
    tuning.setdefault("max_positions_per_second_drop", 0.0)
    tuning.setdefault(
        "variable_definitions",
        {
            "gain": {
                "env_key": tuning.get("gain_env_key", "AIRSPY_ADSB_GAIN"),
                "candidates": tuning.get("candidate_gains", ["auto"]),
            }
        },
    )
    config.setdefault("current_extra_env", {})
    return config


def read_optional_json(config: dict[str, Any], key: str) -> dict[str, Any]:
    path = Path(config["paths"][key])
    if not path.exists():
        return {}
    return load_json(path)


def parse_key_value(text: str) -> tuple[str, str]:
    if "=" not in text:
        raise ValueError(f"Expected KEY=VALUE, got: {text}")
    key, value = text.split("=", 1)
    key = key.strip()
    if not key:
        raise ValueError(f"Missing key in override: {text}")
    return key, value


def build_env_map(config: dict[str, Any], overrides: dict[str, str] | None = None) -> dict[str, str]:
    env_map: dict[str, str] = {}
    base = config.get("current_extra_env", {})
    if isinstance(base, dict):
        for key, value in base.items():
            env_map[str(key)] = str(value)
    if overrides:
        for key, value in overrides.items():
            env_map[str(key)] = str(value)
    return env_map


def env_map_to_block(env_map: dict[str, str]) -> str:
    return "\n".join(f"{key}={value}" for key, value in env_map.items())


def collect_overrides(items: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for item in items:
        key, value = parse_key_value(item)
        overrides[key] = value
    return overrides


def state_dir(config: dict[str, Any]) -> Path:
    return Path(config["output"]["state_dir"])


def live_state_paths(config: dict[str, Any]) -> dict[str, Path]:
    base = state_dir(config)
    return {
        "last_applied": base / "last-applied-env.latest.json",
        "last_transaction": base / "last-transaction.latest.json",
        "last_response": base / "last-controller-response.latest.json",
    }


def http_request(url: str, method: str = "GET", data: dict[str, str] | None = None) -> tuple[int, str]:
    encoded = None
    headers: dict[str, str] = {}
    if data is not None:
        encoded = urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = Request(url, data=encoded, method=method, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            status = getattr(response, "status", 200)
            body = response.read().decode("utf-8", errors="replace")
            return status, body
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body
    except URLError as exc:
        raise RuntimeError(f"Request to {url} failed: {exc}") from exc


def apply_extra_env(config: dict[str, Any], env_map: dict[str, str], reason: str) -> dict[str, Any]:
    controller = config["controller"]
    tuning = config["tuning"]
    paths = live_state_paths(config)
    block = env_map_to_block(env_map)
    form_data = {
        str(tuning["env_field"]): block,
        str(tuning["submit_field"]): str(tuning["submit_value"]),
    }
    expert_url = controller["base_url"].rstrip("/") + controller["expert_path"]
    restart_url = controller["base_url"].rstrip("/") + controller["restart_path"]

    previous = build_env_map(config)
    logger.info("Posting env to %s (reason: %s)", expert_url, reason)
    status, body = http_request(expert_url, method="POST", data=form_data)
    response_record = {
        "captured_at": utc_now_iso(),
        "expert_url": expert_url,
        "status": status,
        "body_preview": body[:1000],
        "submitted_fields": form_data,
    }
    write_json(paths["last_response"], response_record)
    if status >= 400:
        raise RuntimeError(f"Expert POST failed with HTTP {status}")

    deadline = time.monotonic() + float(controller["restart_timeout_seconds"])
    restart_checks: list[dict[str, Any]] = []
    final_body = ""
    final_status = None
    while time.monotonic() < deadline:
        logger.debug("Polling %s for restart completion", restart_url)
        poll_status, poll_body = http_request(restart_url, method="GET")
        final_status = poll_status
        final_body = poll_body.strip()
        restart_checks.append(
            {
                "checked_at": utc_now_iso(),
                "status": poll_status,
                "body": final_body,
            }
        )
        if poll_body.strip() == "done":
            break
        time.sleep(float(controller["restart_poll_seconds"]))
    else:
        raise RuntimeError("Timed out waiting for /restart to return done")

    settle_seconds = float(controller["settle_seconds"])
    if settle_seconds > 0:
        time.sleep(settle_seconds)

    applied_record = {
        "applied_at": utc_now_iso(),
        "reason": reason,
        "env_map": env_map,
        "env_block": block,
        "expert_url": expert_url,
        "restart_url": restart_url,
        "restart_status": final_status,
        "restart_body": final_body,
    }
    transaction = {
        "captured_at": utc_now_iso(),
        "reason": reason,
        "previous_env_map": previous,
        "new_env_map": env_map,
        "restart_checks": restart_checks,
    }
    write_json(paths["last_applied"], applied_record)
    write_json(paths["last_transaction"], transaction)
    config["current_extra_env"] = env_map
    return applied_record


def collect_snapshot(config: dict[str, Any]) -> dict[str, Any]:
    airspy = read_optional_json(config, "airspy_stats")
    readsb_stats = read_optional_json(config, "readsb_stats")
    readsb_status = read_optional_json(config, "readsb_status")
    readsb_receiver = read_optional_json(config, "readsb_receiver")
    aircraft = read_optional_json(config, "readsb_aircraft")

    last1 = readsb_stats.get("last1min", {})
    airspy_summary = {
        "gain": airspy.get("gain"),
        "samplerate": airspy.get("samplerate"),
        "lost_buffers": airspy.get("lost_buffers", 0),
        "median_rssi": safe_float(airspy.get("rssi", {}).get("median")),
        "median_snr": safe_float(airspy.get("snr", {}).get("median")),
        "median_noise": safe_float(airspy.get("noise", {}).get("median")),
        "airspy_messages_per_second": sum(
            value for value in airspy.get("df_counts", []) if isinstance(value, int)
        ) / 60.0,
    }
    live = summarize_aircraft(aircraft)
    max_range_m = safe_float(last1.get("max_distance"))

    return {
        "captured_at": utc_now_iso(),
        "station_name": config.get("station_name"),
        "mode": config.get("mode", "dry-run"),
        "receiver_version": readsb_receiver.get("version"),
        "airspy": airspy_summary,
        "readsb": {
            "aircraft_with_pos": readsb_status.get("aircraft_with_pos", 0),
            "aircraft_without_pos": readsb_status.get("aircraft_without_pos", 0),
            "messages_per_second": (safe_float(last1.get("messages")) or 0.0) / 60.0,
            "positions_per_second": (safe_float(last1.get("position_count_total")) or 0.0) / 60.0,
            "max_range_nm": (max_range_m or 0.0) / 1852.0,
            "global_cpr_ok": last1.get("cpr", {}).get("global_ok", 0),
            "local_cpr_ok": last1.get("cpr", {}).get("local_ok", 0),
            "remote_bytes_in_per_second": (safe_float(last1.get("remote", {}).get("bytes_in")) or 0.0) / 60.0,
            "remote_bytes_out_per_second": (safe_float(last1.get("remote", {}).get("bytes_out")) or 0.0) / 60.0,
        },
        "live": live,
    }


def score_snapshot(snapshot: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    weights = config["scoring"]["weights"]
    airspy = snapshot["airspy"]
    readsb = snapshot["readsb"]
    live = snapshot["live"]

    parts = {
        "aircraft_with_pos": weights["aircraft_with_pos"] * float(readsb["aircraft_with_pos"]),
        "messages_per_second": weights["messages_per_second"] * float(readsb["messages_per_second"]),
        "positions_per_second": weights["positions_per_second"] * float(readsb["positions_per_second"]),
        "max_range_nm": weights["max_range_nm"] * float(readsb["max_range_nm"]),
        "live_range_nm": weights["live_range_nm"] * float(live["farthest_nm"]),
        "strong_signals": weights["strong_signals"] * float(live["strong_count"]),
        "median_snr": weights["median_snr"] * float(airspy["median_snr"] or 0.0),
        "lost_buffers": weights["lost_buffers"] * float(airspy["lost_buffers"] or 0.0),
        "median_noise": weights["median_noise"] * float(airspy["median_noise"] or 0.0),
    }
    total = sum(parts.values())

    return {
        "captured_at": snapshot["captured_at"],
        "score": round(total, 3),
        "parts": {key: round(value, 3) for key, value in parts.items()},
        "snapshot": snapshot,
    }


def capture_scored_snapshot(config: dict[str, Any], label: str) -> dict[str, Any]:
    scored = score_snapshot(collect_snapshot(config), config)
    scored["label"] = label
    return scored


def metric_summary(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "avg": round(sum(values) / len(values), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def observation_metric(scored_samples: list[dict[str, Any]], path: tuple[str, ...]) -> dict[str, float] | None:
    """Extract a nested metric from each scored sample via a key path and return avg/min/max summary."""
    values: list[float] = []
    for sample in scored_samples:
        current: Any = sample
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        if isinstance(current, (int, float)):
            values.append(float(current))
    return metric_summary(values)


def collect_observation(
    config: dict[str, Any],
    label: str,
    warmup_seconds: float,
    observation_seconds: float,
) -> dict[str, Any]:
    if warmup_seconds > 0:
        time.sleep(warmup_seconds)

    sample_interval = max(1.0, float(config["tuning"].get("sample_interval_seconds", 30)))
    sample_count = max(1, int(observation_seconds // sample_interval))
    if observation_seconds > 0 and observation_seconds % sample_interval:
        sample_count += 1
    if observation_seconds <= 0:
        sample_count = 1

    scored_samples: list[dict[str, Any]] = []
    started_at = utc_now_iso()
    logger.info("Collecting %d samples for %s (interval=%.0fs)", sample_count, label, sample_interval)
    for index in range(sample_count):
        logger.debug("Sample %d/%d for %s", index + 1, sample_count, label)
        scored_samples.append(capture_scored_snapshot(config, label=f"{label}-sample-{index + 1}"))
        if index != sample_count - 1:
            time.sleep(sample_interval)
    ended_at = utc_now_iso()

    observation = {
        "label": label,
        "started_at": started_at,
        "ended_at": ended_at,
        "sample_interval_seconds": sample_interval,
        "sample_count": len(scored_samples),
        "score": observation_metric(scored_samples, ("score",)),
        "airspy": {
            "lost_buffers": observation_metric(scored_samples, ("snapshot", "airspy", "lost_buffers")),
            "median_snr": observation_metric(scored_samples, ("snapshot", "airspy", "median_snr")),
            "median_noise": observation_metric(scored_samples, ("snapshot", "airspy", "median_noise")),
        },
        "readsb": {
            "aircraft_with_pos": observation_metric(scored_samples, ("snapshot", "readsb", "aircraft_with_pos")),
            "messages_per_second": observation_metric(scored_samples, ("snapshot", "readsb", "messages_per_second")),
            "positions_per_second": observation_metric(scored_samples, ("snapshot", "readsb", "positions_per_second")),
            "max_range_nm": observation_metric(scored_samples, ("snapshot", "readsb", "max_range_nm")),
        },
        "live": {
            "farthest_nm": observation_metric(scored_samples, ("snapshot", "live", "farthest_nm")),
            "strong_count": observation_metric(scored_samples, ("snapshot", "live", "strong_count")),
        },
        "samples": scored_samples,
    }
    return observation


def compare_metric(metric: dict[str, float] | None, key: str) -> float | None:
    """Extract a named key from a metric summary dict (avg/min/max), returning None if absent."""
    if not isinstance(metric, dict):
        return None
    value = metric.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def candidate_acceptance(
    config: dict[str, Any],
    observation: dict[str, Any],
    best_observation: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Decide whether to accept a candidate observation over the current best.

    Returns (accepted, reasons) where accepted is True when the candidate should
    be promoted and reasons is a list of rejection strings (empty when accepted).
    """
    tuning = config["tuning"]
    minimum_improvement = float(tuning.get("minimum_improvement", 0.0))
    significant_improvement = float(tuning.get("significant_improvement", minimum_improvement))
    max_lost_buffers = int(tuning.get("max_lost_buffers", 0))
    minimum_median_snr = tuning.get("minimum_median_snr")
    if minimum_median_snr is None:
        baseline_snr = config.get("baseline_reference", {}).get("median_snr")
        minimum_median_snr = baseline_snr if baseline_snr is not None else None

    reasons: list[str] = []
    score_avg = compare_metric(observation.get("score"), "avg")
    best_score_avg = compare_metric(best_observation.get("score"), "avg")
    score_delta = (score_avg or 0.0) - (best_score_avg or 0.0)
    if score_delta < minimum_improvement:
        reasons.append(
            f"score delta {score_delta:.3f} below minimum improvement {minimum_improvement:.3f}"
        )

    lost_buffers = compare_metric(observation.get("airspy", {}).get("lost_buffers"), "max")
    if lost_buffers is not None and lost_buffers > max_lost_buffers:
        reasons.append(f"lost buffers {lost_buffers:.3f} above limit {max_lost_buffers}")

    if minimum_median_snr is not None:
        median_snr = compare_metric(observation.get("airspy", {}).get("median_snr"), "avg") or 0.0
        if median_snr < float(minimum_median_snr):
            reasons.append(
                f"median SNR {median_snr:.3f} below minimum {float(minimum_median_snr):.3f}"
            )

    best_aircraft = compare_metric(best_observation.get("readsb", {}).get("aircraft_with_pos"), "avg") or 0.0
    current_aircraft = compare_metric(observation.get("readsb", {}).get("aircraft_with_pos"), "avg") or 0.0
    aircraft_drop = best_aircraft - current_aircraft
    if aircraft_drop > float(tuning.get("max_aircraft_with_pos_drop", 0.0)):
        reasons.append(
            f"aircraft-with-pos drop {aircraft_drop:.3f} above limit {float(tuning.get('max_aircraft_with_pos_drop', 0.0)):.3f}"
        )

    best_msg = compare_metric(best_observation.get("readsb", {}).get("messages_per_second"), "avg") or 0.0
    current_msg = compare_metric(observation.get("readsb", {}).get("messages_per_second"), "avg") or 0.0
    msg_drop = best_msg - current_msg
    if msg_drop > float(tuning.get("max_messages_per_second_drop", 0.0)):
        reasons.append(
            f"message-rate drop {msg_drop:.3f} above limit {float(tuning.get('max_messages_per_second_drop', 0.0)):.3f}"
        )

    best_pos = compare_metric(best_observation.get("readsb", {}).get("positions_per_second"), "avg") or 0.0
    current_pos = compare_metric(observation.get("readsb", {}).get("positions_per_second"), "avg") or 0.0
    pos_drop = best_pos - current_pos
    if pos_drop > float(tuning.get("max_positions_per_second_drop", 0.0)):
        reasons.append(
            f"position-rate drop {pos_drop:.3f} above limit {float(tuning.get('max_positions_per_second_drop', 0.0)):.3f}"
        )

    if minimum_improvement <= score_delta < significant_improvement:
        best_range = compare_metric(best_observation.get("readsb", {}).get("max_range_nm"), "avg") or 0.0
        current_range = compare_metric(observation.get("readsb", {}).get("max_range_nm"), "avg") or 0.0
        best_live_range = compare_metric(best_observation.get("live", {}).get("farthest_nm"), "avg") or 0.0
        current_live_range = compare_metric(observation.get("live", {}).get("farthest_nm"), "avg") or 0.0
        range_gain = current_range - best_range
        live_range_gain = current_live_range - best_live_range
        required_gain = float(tuning.get("marginal_range_gain_nm", 0.0))
        if range_gain < required_gain and live_range_gain < required_gain:
            reasons.append(
                "marginal score improvement without meaningful range gain"
            )

    return len(reasons) == 0, reasons


def write_loop_report(config: dict[str, Any], filename: str, report: dict[str, Any]) -> Path:
    output_path = state_dir(config) / filename
    write_json(output_path, report)
    return output_path


def variable_definition(config: dict[str, Any], variable_name: str) -> dict[str, Any]:
    definitions = config["tuning"].get("variable_definitions", {})
    if not isinstance(definitions, dict) or variable_name not in definitions:
        raise ValueError(f"Unknown variable '{variable_name}'")
    definition = definitions[variable_name]
    if not isinstance(definition, dict):
        raise ValueError(f"Variable definition for '{variable_name}' is invalid")
    env_key = definition.get("env_key")
    candidates = definition.get("candidates")
    if not isinstance(env_key, str) or not env_key:
        raise ValueError(f"Variable '{variable_name}' is missing env_key")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError(f"Variable '{variable_name}' is missing candidates")
    return {"env_key": env_key, "candidates": [str(candidate) for candidate in candidates]}


def command_baseline(args: argparse.Namespace) -> int:
    config = read_config(Path(args.config))
    output_dir = state_dir(config)
    snapshot = collect_snapshot(config)
    out = output_dir / "baseline.latest.json"
    write_json(out, snapshot)
    print(f"Wrote baseline snapshot to {out}")
    return 0


def command_score(args: argparse.Namespace) -> int:
    config = read_config(Path(args.config))
    output_dir = state_dir(config)
    snapshot = collect_snapshot(config)
    scored = score_snapshot(snapshot, config)
    out = output_dir / "score.latest.json"
    write_json(out, scored)
    print(f"Score: {scored['score']}")
    print(f"Wrote scored snapshot to {out}")
    return 0


def command_plan_gain_sweep(args: argparse.Namespace) -> int:
    config = read_config(Path(args.config))
    output_dir = state_dir(config)
    variable_name = getattr(args, "variable", None) or str(config["tuning"].get("variable", "gain"))
    variable = variable_definition(config, variable_name)
    baseline = score_snapshot(collect_snapshot(config), config)
    observation_seconds = int(config["tuning"]["observation_seconds"])
    warmup_seconds = int(config["tuning"]["warmup_seconds"])
    candidates = variable["candidates"]

    experiments = []
    for index, candidate in enumerate(candidates, start=1):
        experiments.append(
            {
                "step": index,
                "mode": config.get("mode", "dry-run"),
                "variable": variable_name,
                "env_key": variable["env_key"],
                "candidate": candidate,
                "warmup_seconds": warmup_seconds,
                "observation_seconds": observation_seconds,
                "sample_interval_seconds": float(config["tuning"].get("sample_interval_seconds", 30)),
                "baseline_score": baseline["score"],
                "apply_action": (
                    "NO-OP in dry-run; live loop will update Expert env, restart the stack, and sample repeatedly"
                ),
                "success_criteria": {
                    "minimum_score_delta": float(config["tuning"].get("minimum_improvement", 0.0)),
                    "significant_improvement": float(
                        config["tuning"].get("significant_improvement", config["tuning"].get("minimum_improvement", 0.0))
                    ),
                    "max_lost_buffers": int(config["tuning"].get("max_lost_buffers", 0)),
                    "minimum_median_snr": baseline["snapshot"]["airspy"]["median_snr"],
                    "marginal_range_gain_nm": float(config["tuning"].get("marginal_range_gain_nm", 0.0)),
                },
            }
        )

    plan = {
        "generated_at": utc_now_iso(),
        "station_name": config.get("station_name"),
        "mode": config.get("mode", "dry-run"),
        "variable": variable_name,
        "env_key": variable["env_key"],
        "baseline": baseline,
        "experiments": experiments,
        "notes": [
            "Run only one gain candidate at a time.",
            "Observe candidates with repeated samples before promoting one.",
            "Marginal gains should not degrade aircraft, message, or position rates.",
        ],
    }

    out = output_dir / f"{variable_name}-sweep-plan.latest.json"
    write_json(out, plan)
    print(f"Wrote variable sweep plan to {out}")
    return 0


def command_render_extra_env(args: argparse.Namespace) -> int:
    config = read_config(Path(args.config))
    overrides = collect_overrides(args.set or [])
    env_map = build_env_map(config, overrides=overrides)
    block = env_map_to_block(env_map)
    print(block)
    return 0


def command_apply_extra_env(args: argparse.Namespace) -> int:
    config = read_config(Path(args.config))
    overrides = collect_overrides(args.set or [])
    env_map = build_env_map(config, overrides=overrides)

    if args.dry_run:
        print(env_map_to_block(env_map))
        print("Dry run only; no POST sent.")
        return 0

    applied = apply_extra_env(config, env_map, reason=args.reason or "manual apply-extra-env")
    print(f"Applied {len(env_map)} environment variables via {applied['expert_url']}")
    print(f"Restart completed with body: {applied['restart_body']}")
    return 0


def command_apply_gain(args: argparse.Namespace) -> int:
    config = read_config(Path(args.config))
    gain_key = str(config["tuning"]["gain_env_key"])
    env_map = build_env_map(config, overrides={gain_key: args.gain})

    if args.dry_run:
        print(env_map_to_block(env_map))
        print("Dry run only; no POST sent.")
        return 0

    applied = apply_extra_env(config, env_map, reason=f"apply gain {args.gain}")
    print(f"Applied {gain_key}={args.gain} via {applied['expert_url']}")
    print(f"Restart completed with body: {applied['restart_body']}")
    return 0


def command_rollback_last(args: argparse.Namespace) -> int:
    config = read_config(Path(args.config))
    paths = live_state_paths(config)
    if not paths["last_transaction"].exists():
        raise SystemExit("No previous transaction found to roll back.")

    transaction = load_json(paths["last_transaction"])
    previous_env_map = transaction.get("previous_env_map", {})
    if not isinstance(previous_env_map, dict):
        raise SystemExit("Rollback data is invalid.")

    if args.dry_run:
        print(env_map_to_block({str(k): str(v) for k, v in previous_env_map.items()}))
        print("Dry run only; no POST sent.")
        return 0

    applied = apply_extra_env(
        config,
        {str(k): str(v) for k, v in previous_env_map.items()},
        reason="rollback last transaction",
    )
    print(f"Rolled back environment via {applied['expert_url']}")
    print(f"Restart completed with body: {applied['restart_body']}")
    return 0


def _collect_baseline_observation(
    config: dict[str, Any],
    variable_name: str,
    gain_key: str,
    candidates: list[str],
    observation_seconds: float,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Collect baseline and return (baseline_gain, baseline_env_map, baseline_observation)."""
    baseline_env_map = build_env_map(config)
    tuning = config["tuning"]
    baseline_gain = baseline_env_map.get(gain_key, str(tuning.get("baseline_gain", candidates[0])))
    logger.info("Collecting baseline for %s (gain=%s)", variable_name, baseline_gain)
    baseline_observation = collect_observation(
        config,
        label=f"{variable_name}-baseline",
        warmup_seconds=0.0,
        observation_seconds=observation_seconds,
    )
    config["baseline_reference"] = {
        "score": compare_metric(baseline_observation.get("score"), "avg"),
        "median_snr": compare_metric(baseline_observation.get("airspy", {}).get("median_snr"), "avg"),
    }
    logger.info(
        "Baseline: gain=%s score=%s snr=%s",
        baseline_gain,
        config["baseline_reference"]["score"],
        config["baseline_reference"]["median_snr"],
    )
    return baseline_gain, baseline_env_map, baseline_observation


def _test_candidate(
    config: dict[str, Any],
    variable_name: str,
    gain_key: str,
    candidate: str,
    best_gain: str,
    best_env_map: dict[str, str],
    best_observation: dict[str, Any],
    warmup_seconds: float,
    observation_seconds: float,
    rollback_on_reject: bool,
    step: int = 0,
    total: int = 0,
) -> tuple[dict[str, Any], str, dict[str, str], dict[str, Any], Exception | None]:
    """Apply one candidate, observe it, and accept or roll back.

    Returns (candidate_record, best_gain, best_env_map, best_observation, error_or_none).
    On error, rollback is attempted before returning; caller is responsible for aborting the loop.
    """
    step_str = f"[{step}/{total}] " if step and total else ""
    candidate_env_map = build_env_map(config, overrides={gain_key: candidate})
    candidate_record: dict[str, Any] = {
        "variable": variable_name,
        "env_key": gain_key,
        "candidate": candidate,
        "started_at": utc_now_iso(),
    }

    try:
        logger.info("Testing candidate %s=%s", gain_key, candidate)
        print(f"{step_str}Testing {gain_key}={candidate} ...")
        apply_result = apply_extra_env(
            config, candidate_env_map, reason=f"auto {variable_name} candidate {candidate}"
        )
        candidate_record["apply_result"] = apply_result

        old_best_score = compare_metric(best_observation.get("score"), "avg")
        observation = collect_observation(
            config,
            label=f"{variable_name}-candidate-{candidate}",
            warmup_seconds=warmup_seconds,
            observation_seconds=observation_seconds,
        )
        accepted, reasons = candidate_acceptance(config, observation, best_observation)
        candidate_record["observation"] = observation
        candidate_record["accepted"] = accepted
        candidate_record["reasons"] = reasons
        logger.info("Candidate %s=%s: accepted=%s reasons=%s", gain_key, candidate, accepted, reasons)

        if accepted:
            score_avg = compare_metric(observation.get("score"), "avg")
            delta = (score_avg or 0.0) - (old_best_score or 0.0)
            score_str = f"  score {score_avg:.2f} ({delta:+.2f})" if score_avg is not None else ""
            print(f"{step_str}{gain_key}={candidate}: accepted{score_str}")
            best_gain = candidate
            best_env_map = dict(candidate_env_map)
            best_observation = observation
            config["current_extra_env"] = dict(candidate_env_map)
            candidate_record["result"] = "accepted"
        else:
            reasons_str = " | ".join(reasons[:2])
            print(f"{step_str}{gain_key}={candidate}: rejected  ({reasons_str})")
            candidate_record["result"] = "rejected"
            if rollback_on_reject:
                logger.info("Rolling back rejected candidate %s=%s", gain_key, candidate)
                rollback_result = apply_extra_env(
                    config,
                    best_env_map,
                    reason=f"rollback rejected candidate {candidate}",
                )
                config["current_extra_env"] = dict(best_env_map)
                candidate_record["rollback_result"] = rollback_result
    except Exception as exc:
        candidate_record["result"] = "error"
        candidate_record["error"] = str(exc)
        logger.exception("Error testing candidate %s=%s", gain_key, candidate)
        if rollback_on_reject:
            try:
                rollback_result = apply_extra_env(
                    config,
                    best_env_map,
                    reason=f"rollback failed candidate {candidate}",
                )
                config["current_extra_env"] = dict(best_env_map)
                candidate_record["rollback_result"] = rollback_result
            except Exception as rollback_exc:
                logger.exception("Rollback also failed: %s", rollback_exc)
        return candidate_record, best_gain, best_env_map, best_observation, exc

    return candidate_record, best_gain, best_env_map, best_observation, None


def command_auto_gain_loop(args: argparse.Namespace) -> int:
    config = read_config(Path(args.config))
    tuning = config["tuning"]
    variable_name = getattr(args, "variable", None) or str(tuning.get("variable", "gain"))
    variable = variable_definition(config, variable_name)
    gain_key = variable["env_key"]
    candidates = variable["candidates"]
    warmup_seconds = float(tuning["warmup_seconds"])
    observation_seconds = float(tuning["observation_seconds"])
    rollback_on_reject = bool(tuning.get("rollback_on_reject", True))

    baseline_gain, baseline_env_map, baseline_observation = _collect_baseline_observation(
        config, variable_name, gain_key, candidates, observation_seconds
    )

    best_gain = baseline_gain
    best_env_map = dict(baseline_env_map)
    best_observation = baseline_observation
    history: list[dict[str, Any]] = [
        {
            "variable": variable_name,
            "candidate": baseline_gain,
            "result": "baseline",
            "observation": baseline_observation,
        }
    ]

    if args.dry_run:
        report = {
            "generated_at": utc_now_iso(),
            "mode": "dry-run",
            "variable": variable_name,
            "env_key": gain_key,
            "baseline_value": baseline_gain,
            "best_value": best_gain,
            "best_score": compare_metric(best_observation.get("score"), "avg"),
            "history": history,
            "plan": [
                {
                    "candidate": candidate,
                    "warmup_seconds": warmup_seconds,
                    "observation_seconds": observation_seconds,
                    "sample_interval_seconds": float(tuning.get("sample_interval_seconds", 30)),
                }
                for candidate in candidates
            ],
        }
        out = write_loop_report(config, f"auto-{variable_name}-loop.latest.json", report)

        baseline_score = compare_metric(baseline_observation.get("score"), "avg")
        warmup_min = int(warmup_seconds // 60)
        obs_min = int(observation_seconds // 60)
        testable = [c for c in candidates if c != baseline_gain]
        est_minutes = int(len(testable) * (warmup_seconds + observation_seconds) // 60)

        print(f"=== {variable_name} sweep plan (dry-run) ===")
        print()
        score_str = f"  (score {baseline_score:.2f})" if baseline_score is not None else ""
        print(f"Variable : {gain_key}")
        print(f"Baseline : {baseline_gain}{score_str}")
        print()
        print(f"Candidates ({len(candidates)} total):")
        for idx, candidate in enumerate(candidates, start=1):
            if candidate == baseline_gain:
                print(f"  {idx}. {candidate:<12} [skip - current best]")
            else:
                print(f"  {idx}. {candidate:<12} warmup {warmup_min}m + obs {obs_min}m")
        print()
        print(f"Estimated time : ~{est_minutes} min total")

        other_env = {k: v for k, v in config.get("current_extra_env", {}).items() if k != gain_key}
        if other_env:
            other_str = "  ".join(f"{k}={v}" for k, v in list(other_env.items())[:4])
            print(f"Other settings (not changed): {other_str}")

        print()
        print(f"When the plan looks right, run:  loop {variable_name} live")
        print(f"Full plan written to: {out}")
        return 0

    for idx, candidate in enumerate(candidates, start=1):
        if candidate == best_gain:
            print(f"[{idx}/{len(candidates)}] {gain_key}={candidate}: skip (current best)")
            history.append(
                {
                    "variable": variable_name,
                    "candidate": candidate,
                    "result": "skipped-current-best",
                    "observation": best_observation,
                }
            )
            continue

        candidate_record, best_gain, best_env_map, best_observation, error = _test_candidate(
            config, variable_name, gain_key, candidate,
            best_gain, best_env_map, best_observation,
            warmup_seconds, observation_seconds, rollback_on_reject,
            step=idx, total=len(candidates),
        )
        history.append(candidate_record)

        if error is not None:
            report = {
                "generated_at": utc_now_iso(),
                "mode": "live",
                "variable": variable_name,
                "env_key": gain_key,
                "baseline_value": baseline_gain,
                "best_value": best_gain,
                "best_score": compare_metric(best_observation.get("score"), "avg"),
                "history": history,
            }
            out = write_loop_report(config, f"auto-{variable_name}-loop.latest.json", report)
            raise SystemExit(f"Auto loop aborted on {candidate}; details written to {out}") from error

    report = {
        "generated_at": utc_now_iso(),
        "mode": "live",
        "variable": variable_name,
        "env_key": gain_key,
        "baseline_value": baseline_gain,
        "baseline_score": compare_metric(baseline_observation.get("score"), "avg"),
        "best_value": best_gain,
        "best_score": compare_metric(best_observation.get("score"), "avg"),
        "history": history,
    }
    out = write_loop_report(config, f"auto-{variable_name}-loop.latest.json", report)
    score_best = compare_metric(best_observation.get("score"), "avg")
    score_baseline = compare_metric(baseline_observation.get("score"), "avg")
    if score_best is not None and score_baseline is not None:
        delta = score_best - score_baseline
        print(f"Done. {gain_key}: {baseline_gain} → {best_gain}  score {score_baseline:.2f} → {score_best:.2f} ({delta:+.2f})")
    else:
        print(f"Done. Best {gain_key}={best_gain} (was {baseline_gain})")
    print(f"Loop report: {out}")
    result_data: dict[str, Any] = {
        "variable": variable_name,
        "env_key": gain_key,
        "best": best_gain,
        "baseline": baseline_gain,
    }
    if score_best is not None:
        result_data["score_best"] = score_best
    if score_baseline is not None:
        result_data["score_baseline"] = score_baseline
    print(f"LOOP_RESULT:{json.dumps(result_data)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ADS-B SDR autotune toolkit")
    parser.add_argument("--version", action="version", version="adsb-autotune phase2")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name, func in (
        ("baseline", command_baseline),
        ("score", command_score),
        ("plan-gain-sweep", command_plan_gain_sweep),
    ):
        sub = subparsers.add_parser(name)
        sub.add_argument("--config", required=True, help="Path to config JSON")
        if name == "plan-gain-sweep":
            sub.add_argument("--variable", default="", help="Variable definition to plan")
        sub.set_defaults(func=func)

    render_sub = subparsers.add_parser("render-extra-env")
    render_sub.add_argument("--config", required=True, help="Path to config JSON")
    render_sub.add_argument("--set", action="append", default=[], help="Override in KEY=VALUE form")
    render_sub.set_defaults(func=command_render_extra_env)

    apply_sub = subparsers.add_parser("apply-extra-env")
    apply_sub.add_argument("--config", required=True, help="Path to config JSON")
    apply_sub.add_argument("--set", action="append", default=[], help="Override in KEY=VALUE form")
    apply_sub.add_argument("--reason", default="", help="Reason stored in state history")
    apply_sub.add_argument("--dry-run", action="store_true", help="Render without sending POST")
    apply_sub.set_defaults(func=command_apply_extra_env)

    gain_sub = subparsers.add_parser("apply-gain")
    gain_sub.add_argument("--config", required=True, help="Path to config JSON")
    gain_sub.add_argument("--gain", required=True, help="Gain value written to the configured gain env key")
    gain_sub.add_argument("--dry-run", action="store_true", help="Render without sending POST")
    gain_sub.set_defaults(func=command_apply_gain)

    rollback_sub = subparsers.add_parser("rollback-last")
    rollback_sub.add_argument("--config", required=True, help="Path to config JSON")
    rollback_sub.add_argument("--dry-run", action="store_true", help="Render without sending POST")
    rollback_sub.set_defaults(func=command_rollback_last)

    auto_gain_sub = subparsers.add_parser("auto-gain-loop")
    auto_gain_sub.add_argument("--config", required=True, help="Path to config JSON")
    auto_gain_sub.add_argument("--variable", default="", help="Variable definition to tune")
    auto_gain_sub.add_argument("--dry-run", action="store_true", help="Plan the loop without live POSTs")
    auto_gain_sub.set_defaults(func=command_auto_gain_loop)

    auto_loop_sub = subparsers.add_parser("auto-loop")
    auto_loop_sub.add_argument("--config", required=True, help="Path to config JSON")
    auto_loop_sub.add_argument("--variable", required=True, help="Variable definition to tune")
    auto_loop_sub.add_argument("--dry-run", action="store_true", help="Plan the loop without live POSTs")
    auto_loop_sub.set_defaults(func=command_auto_gain_loop)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
