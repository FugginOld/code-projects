#!/usr/bin/env python3
"""Shared utilities for adsb_tui and autotune."""

from __future__ import annotations

from typing import Any

STRONG_RSSI_THRESHOLD = -20.0


def safe_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def summarize_aircraft(aircraft_json: dict[str, Any]) -> dict[str, Any]:
    """Return a summary dict of live aircraft from a readsb aircraft.json payload.

    Keys: total, with_pos, grounded, closest_nm, farthest_nm, strongest_rssi, strong_count.
    farthest_nm is 0.0 when no aircraft with range data are present.
    """
    aircraft = aircraft_json.get("aircraft", [])
    if not isinstance(aircraft, list):
        aircraft = []

    with_pos = 0
    grounded = 0
    strong_count = 0
    closest: float | None = None
    farthest = 0.0
    strongest: float | None = None

    for entry in aircraft:
        if not isinstance(entry, dict):
            continue
        if "lat" in entry and "lon" in entry:
            with_pos += 1
        altitude = entry.get("alt_baro")
        if isinstance(altitude, (int, float)) and altitude <= 1500:
            grounded += 1
        distance = safe_float(entry.get("r_dst"))
        if distance is not None:
            closest = distance if closest is None else min(closest, distance)
            farthest = max(farthest, distance)
        rssi = safe_float(entry.get("rssi"))
        if rssi is not None:
            strongest = rssi if strongest is None else max(strongest, rssi)
            if rssi >= STRONG_RSSI_THRESHOLD:
                strong_count += 1

    return {
        "total": len(aircraft),
        "with_pos": with_pos,
        "grounded": grounded,
        "closest_nm": closest,
        "farthest_nm": farthest,
        "strongest_rssi": strongest,
        "strong_count": strong_count,
    }
