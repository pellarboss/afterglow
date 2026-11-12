"""Hardware-free tests: colour conversion, theme definitions and sunset maths.

Run with:  .venv/bin/python -m pytest -q
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hue_homekit  # noqa: E402
import sunset_auto  # noqa: E402
import themes  # noqa: E402

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


# --- Colour conversion -------------------------------------------------------
@pytest.mark.parametrize("hue", [0, 30, 60, 120, 180, 240, 300])
def test_hs_xy_round_trip(hue):
    x, y = hue_homekit.hs_to_xy(hue, 100)
    assert 0 < x < 1 and 0 < y < 1
    h2, s2 = hue_homekit.xy_to_hs(x, y)
    diff = min(abs(h2 - hue), 360 - abs(h2 - hue))
    assert diff < 2, f"hue {hue} came back as {h2}"
    assert s2 > 95


def test_white_maps_near_neutral():
    # Hue's wide-gamut matrix puts RGB white slightly warm of D65 (0.3127, 0.3290).
    x, y = hue_homekit.hs_to_xy(0, 0)
    assert abs(x - 0.3127) < 0.02 and abs(y - 0.3290) < 0.02


def test_xy_to_hs_handles_zero_y():
    assert hue_homekit.xy_to_hs(0.3, 0) == (0.0, 0.0)


# --- Themes -----------------------------------------------------------------
def test_theme_keys_unique_and_indexed():
    keys = [t.key for t in themes._THEMES]
    assert len(keys) == len(set(keys))
    assert set(themes.THEMES) == set(keys)


@pytest.mark.parametrize("theme", themes._THEMES, ids=lambda t: t.key)
def test_theme_is_well_formed(theme):
    assert theme.group in themes.GROUPS
    assert theme.interval_s >= 8, "nothing should change faster than every 8 s"
    assert theme.fade_ms > 0
    assert len(theme.colours) >= 3
    for c in theme.colours:
        assert HEX.match(c.hex), c
        assert 1 <= c.brightness <= 100, c
        is_white = c.mireds is not None
        is_colour = c.hue is not None and c.sat is not None
        assert is_white != is_colour, c
        if is_white:
            assert hue_homekit.MIN_MIREDS <= c.mireds <= hue_homekit.MAX_MIREDS, c


def test_every_group_has_themes():
    for group in themes.GROUPS:
        assert themes.themes_in(group)


# --- Sunset -----------------------------------------------------------------
def test_sun_times_melbourne_midsummer():
    tz = dt.timezone(dt.timedelta(hours=11))
    times = sunset_auto.sun_times({}, dt.date(2026, 12, 21), tz)
    assert times is not None
    assert 20 <= times["sunset"].hour <= 21  # Melbourne sunsets around 8:40 pm in December
    assert times["start"] < times["sunset"] < times["dusk"] <= times["full"]


# --- Website data -----------------------------------------------------------
def test_website_themes_match_code():
    """docs/_data/themes.json drives the website; keep it in step with themes.py."""
    import json

    data = json.loads((Path(__file__).resolve().parents[1] / "docs/_data/themes.json").read_text())
    assert [d["key"] for d in data] == [t.key for t in themes._THEMES]
    for d, t in zip(data, themes._THEMES):
        assert d["name"] == t.name and d["group"] == t.group
        assert d["interval_s"] == t.interval_s and d["fade_ms"] == t.fade_ms
        assert [c["hex"] for c in d["colours"]] == [c.hex for c in t.colours]
