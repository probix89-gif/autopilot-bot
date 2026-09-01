"""Tests: fingerprint profiles + stealth JS generation."""

from autopilot.engine.fingerprint import generate_fingerprint, ProfileDatabase
from autopilot.engine.stealth import build_stealth_js


def test_fingerprint_unique():
    a = generate_fingerprint()
    b = generate_fingerprint()
    assert a.canvas_noise_seed != b.canvas_noise_seed
    assert a.user_agent != b.user_agent or a.id != b.id


def test_fingerprint_fields():
    fp = generate_fingerprint()
    assert fp.canvas_noise_seed > 0
    assert fp.cpu_cores in (2, 4, 8)
    assert fp.screen_width >= 1280
    assert fp.user_agent.startswith("Mozilla/5.0")


def test_profile_db_reuse():
    db = ProfileDatabase()
    fp1 = db.get_or_create("tab_0")
    fp2 = db.get_or_create("tab_0")
    assert fp1.id == fp2.id  # same profile reused per tab


def test_stealth_js_contains_overrides():
    fp = generate_fingerprint()
    js = build_stealth_js(fp)
    assert "getImageData" in js
    assert fp.gl_vendor in js
    assert "16807" in js  # PRNG multiplier
    assert fp.platform in js
