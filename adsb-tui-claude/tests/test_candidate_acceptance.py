"""Unit tests for candidate_acceptance() in autotune.py."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from autotune import candidate_acceptance


def _ms(avg: float) -> dict[str, float]:
    return {"avg": avg, "min": avg, "max": avg}


def _obs(
    score: float,
    aircraft: float = 50.0,
    messages: float = 100.0,
    positions: float = 10.0,
    max_range: float = 100.0,
    farthest: float = 80.0,
    lost_buffers: float = 0.0,
    median_snr: float = 15.0,
) -> dict:
    return {
        "score": _ms(score),
        "airspy": {"lost_buffers": _ms(lost_buffers), "median_snr": _ms(median_snr)},
        "readsb": {
            "aircraft_with_pos": _ms(aircraft),
            "messages_per_second": _ms(messages),
            "positions_per_second": _ms(positions),
            "max_range_nm": _ms(max_range),
        },
        "live": {"farthest_nm": _ms(farthest)},
    }


def _cfg(
    minimum_improvement: float = 0.0,
    significant_improvement: float | None = None,
    max_lost_buffers: int = 0,
    minimum_median_snr: float | None = None,
    max_aircraft_drop: float = 0.0,
    max_msg_drop: float = 0.0,
    max_pos_drop: float = 0.0,
    marginal_range_gain: float = 0.0,
) -> dict:
    return {
        "tuning": {
            "minimum_improvement": minimum_improvement,
            "significant_improvement": significant_improvement if significant_improvement is not None else minimum_improvement,
            "max_lost_buffers": max_lost_buffers,
            "minimum_median_snr": minimum_median_snr,
            "max_aircraft_with_pos_drop": max_aircraft_drop,
            "max_messages_per_second_drop": max_msg_drop,
            "max_positions_per_second_drop": max_pos_drop,
            "marginal_range_gain_nm": marginal_range_gain,
        },
        "scoring": {"weights": {}},
    }


def test_basic_accept() -> None:
    accepted, reasons = candidate_acceptance(_cfg(), _obs(11.0), _obs(10.0))
    assert accepted
    assert reasons == []


def test_score_below_minimum_improvement() -> None:
    accepted, reasons = candidate_acceptance(_cfg(minimum_improvement=1.0), _obs(10.5), _obs(10.0))
    assert not accepted
    assert any("score delta" in r for r in reasons)


def test_score_exactly_at_minimum_accepted() -> None:
    accepted, reasons = candidate_acceptance(_cfg(minimum_improvement=0.5), _obs(10.5), _obs(10.0))
    assert accepted


def test_lost_buffers_above_limit() -> None:
    accepted, reasons = candidate_acceptance(_cfg(max_lost_buffers=0), _obs(11.0, lost_buffers=1.0), _obs(10.0))
    assert not accepted
    assert any("lost buffers" in r for r in reasons)


def test_lost_buffers_within_limit() -> None:
    accepted, reasons = candidate_acceptance(_cfg(max_lost_buffers=5), _obs(11.0, lost_buffers=3.0), _obs(10.0))
    assert accepted


def test_snr_below_minimum() -> None:
    accepted, reasons = candidate_acceptance(
        _cfg(minimum_median_snr=15.0),
        _obs(11.0, median_snr=12.0),
        _obs(10.0, median_snr=16.0),
    )
    assert not accepted
    assert any("SNR" in r for r in reasons)


def test_snr_at_minimum_accepted() -> None:
    accepted, reasons = candidate_acceptance(
        _cfg(minimum_median_snr=15.0),
        _obs(11.0, median_snr=15.0),
        _obs(10.0),
    )
    assert accepted


def test_aircraft_drop_above_limit() -> None:
    accepted, reasons = candidate_acceptance(
        _cfg(max_aircraft_drop=5.0),
        _obs(11.0, aircraft=40.0),
        _obs(10.0, aircraft=50.0),
    )
    assert not accepted
    assert any("aircraft-with-pos drop" in r for r in reasons)


def test_aircraft_drop_within_limit() -> None:
    accepted, reasons = candidate_acceptance(
        _cfg(max_aircraft_drop=10.0),
        _obs(11.0, aircraft=45.0),
        _obs(10.0, aircraft=50.0),
    )
    assert accepted


def test_message_rate_drop_above_limit() -> None:
    accepted, reasons = candidate_acceptance(
        _cfg(max_msg_drop=5.0),
        _obs(11.0, messages=80.0),
        _obs(10.0, messages=100.0),
    )
    assert not accepted
    assert any("message-rate drop" in r for r in reasons)


def test_position_rate_drop_above_limit() -> None:
    accepted, reasons = candidate_acceptance(
        _cfg(max_pos_drop=2.0),
        _obs(11.0, positions=5.0),
        _obs(10.0, positions=10.0),
    )
    assert not accepted
    assert any("position-rate drop" in r for r in reasons)


def test_marginal_score_without_range_gain_rejected() -> None:
    # score delta = 0.8, which is in [minimum=0.5, significant=2.0), so range check applies
    accepted, reasons = candidate_acceptance(
        _cfg(minimum_improvement=0.5, significant_improvement=2.0, marginal_range_gain=5.0),
        _obs(10.8, max_range=100.5, farthest=80.5),
        _obs(10.0, max_range=100.0, farthest=80.0),
    )
    assert not accepted
    assert any("marginal" in r for r in reasons)


def test_marginal_score_with_sufficient_range_gain_accepted() -> None:
    # range gain of 10 > marginal_range_gain of 5
    accepted, reasons = candidate_acceptance(
        _cfg(minimum_improvement=0.5, significant_improvement=2.0, marginal_range_gain=5.0),
        _obs(10.8, max_range=110.0, farthest=80.5),
        _obs(10.0, max_range=100.0, farthest=80.0),
    )
    assert accepted


def test_significant_score_skips_range_check() -> None:
    # delta = 2.1 >= significant_improvement = 2.0, no range check
    accepted, reasons = candidate_acceptance(
        _cfg(minimum_improvement=0.5, significant_improvement=2.0, marginal_range_gain=10.0),
        _obs(12.1, max_range=100.5, farthest=80.5),
        _obs(10.0, max_range=100.0, farthest=80.0),
    )
    assert accepted


def test_multiple_rejections_all_reported() -> None:
    accepted, reasons = candidate_acceptance(
        _cfg(max_lost_buffers=0, max_aircraft_drop=0.0),
        _obs(9.0, lost_buffers=2.0, aircraft=45.0),
        _obs(10.0, aircraft=50.0),
    )
    assert not accepted
    assert len(reasons) >= 2


def test_empty_observations_return_no_reasons() -> None:
    # Both empty: all metrics default to 0 so nothing to reject, accepted with no reasons
    accepted, reasons = candidate_acceptance(_cfg(), {}, {})
    assert accepted
    assert reasons == []
