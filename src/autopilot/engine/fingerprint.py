"""Per-tab device fingerprint profile generation (APK-faithful).

Each tab gets a unique profile with its own canvas noise seed, WebGL
vendor/renderer, platform, locale, timezone, UA, and device metrics —
exactly how the APK's DeviceFingerprint + ProfileDatabase work.
"""

import random
import secrets
import string

from autopilot.domain.schemas import DeviceFingerprint
from autopilot.domain.enums import WebRtcPolicy

_PLATFORMS = ["Win32", "MacIntel", "Linux x86_64", "Linux armv8l"]
_LOCALES = ["en-US", "en-GB", "hi-IN", "bn-IN", "en-IN", "de-DE", "fr-FR"]
_TIMEZONES = ["Asia/Kolkata", "Asia/Dhaka", "America/New_York", "Europe/London", "Asia/Dubai"]

_UA_TEMPLATES = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36 Edg/{major}.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36",
]

_VENDORS = [
    ("Google Inc. (Qualcomm)", "ANGLE (Adreno (TM) 640)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA GeForce GTX 1660 Ti Direct3D11 vs_5_0 ps_5_0)"),
    ("Google Inc. (AMD)", "ANGLE (AMD Radeon RX 570 Series Direct3D11 vs_5_0 ps_5_0)"),
    ("Intel", "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0)"),
    ("Google Inc. (Apple)", "ANGLE (Apple, Apple M1, OpenGL 4.1)"),
]

_BUILD_MODELS = [
    ("samsung", "SM-G975F", "SM-G975F"),
    ("samsung", "SM-A525F", "SM-A525F"),
    ("Google", "Pixel 7", "sdk_gphone64_arm64"),
    ("Xiaomi", "Redmi Note 11", "spes"),
    ("OnePlus", "ONEPLUS A6013", "OnePlus6T"),
    ("Motorola", "Moto G82", "rhodei"),
]


def _rand_android_id() -> str:
    return "".join(secrets.choice(string.hexdigits[:16].upper()) for _ in range(16))


def generate_fingerprint(seed: int | None = None) -> DeviceFingerprint:
    """Generate a fresh unique device profile for a tab."""
    rng = random.Random(seed)
    canvas_seed = rng.randint(100000, 999999) if seed is not None else random.randint(100000, 999999)
    audio_seed = rng.randint(100000, 999999) if seed is not None else random.randint(100000, 999999)
    platform = rng.choice(_PLATFORMS)
    locale = rng.choice(_LOCALES)
    vendor, renderer = rng.choice(_VENDORS)
    mfr, model, product = rng.choice(_BUILD_MODELS)
    major = rng.randint(120, 133)

    ua = rng.choice(_UA_TEMPLATES).format(major=major)
    # Desktop vs mobile UA
    if platform == "Win32" or platform == "MacIntel":
        ua = ua  # desktop
    elif platform == "Linux x86_64":
        ua = ua  # linux desktop
    else:
        ua = f"Mozilla/5.0 (Linux; Android 13; {model}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Mobile Safari/537.36"

    languages = [locale]
    if "-" in locale:
        languages.append(locale.split("-")[0])

    return DeviceFingerprint(
        id=secrets.token_hex(4),
        platform=platform,
        user_agent=ua,
        languages=languages,
        locale=locale,
        timezone=rng.choice(_TIMEZONES),
        canvas_noise_seed=canvas_seed,
        audio_noise_seed=audio_seed,
        gl_vendor=vendor,
        gl_renderer=renderer,
        cpu_cores=rng.choice([2, 4, 4, 8]),
        device_memory=rng.choice([4, 8, 8, 16]),
        screen_width=rng.choice([1280, 1366, 1440, 1536, 1920]),
        screen_height=rng.choice([720, 768, 800, 900, 1080]),
        screen_dpi=rng.choice([160, 240, 320]),
        max_touch_points=0 if platform in ("Win32", "MacIntel", "Linux x86_64") else rng.choice([5, 10]),
        build_manufacturer=mfr,
        build_model=model,
        android_id=_rand_android_id(),
        webrtc_policy=rng.choice([WebRtcPolicy.DISABLED, WebRtcPolicy.PROXY_ONLY]),
    )


class ProfileDatabase:
    """Registry of per-tab fingerprints (APK's Z2.b)."""

    def __init__(self) -> None:
        self._profiles: dict[str, DeviceFingerprint] = {}

    def get_or_create(self, tab_id: str) -> DeviceFingerprint:
        if tab_id not in self._profiles:
            self._profiles[tab_id] = generate_fingerprint()
        return self._profiles[tab_id]

    def get(self, tab_id: str) -> DeviceFingerprint | None:
        return self._profiles.get(tab_id)

    def remove(self, tab_id: str) -> None:
        self._profiles.pop(tab_id, None)

    def clear(self) -> None:
        self._profiles.clear()