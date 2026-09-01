"""Pydantic schemas for session config and views (APK-faithful)."""

from pydantic import BaseModel, Field, field_validator

from autopilot.domain.enums import AutomationMode, ProxyProtocol, WebRtcPolicy


class DeviceFingerprint(BaseModel):
    """Per-tab device profile — mirrors APK's DeviceFingerprint."""

    id: str = Field(default="")
    platform: str = Field(default="Win32")
    user_agent: str = Field(default="")
    languages: list[str] = Field(default_factory=lambda: ["en-US", "en"])
    locale: str = Field(default="en-US")
    timezone: str = Field(default="Asia/Kolkata")
    canvas_noise_seed: int = Field(default=1337)
    audio_noise_seed: int = Field(default=1337)
    gl_vendor: str = Field(default="Google Inc. (Qualcomm)")
    gl_renderer: str = Field(default="ANGLE (Adreno (TM) 640)")
    cpu_cores: int = Field(default=4)
    device_memory: int = Field(default=8)
    screen_width: int = Field(default=1280)
    screen_height: int = Field(default=720)
    screen_dpi: int = Field(default=160)
    max_touch_points: int = Field(default=0)
    build_manufacturer: str = Field(default="samsung")
    build_model: str = Field(default="SM-G975F")
    android_id: str = Field(default="")
    webrtc_policy: WebRtcPolicy = WebRtcPolicy.DISABLED


class AutomationConfig(BaseModel):
    """Session automation settings — mirrors APK's AutomationConfig.

    Defaults match the APK: 5 tabs, refresh 30s, scroll 10s, randomize on.
    """

    mode: AutomationMode = AutomationMode.SIMPLE_SCROLL
    tab_count: int = Field(default=5, ge=1, le=8)
    refresh_interval_sec: int = Field(default=30, ge=10)
    scroll_interval_sec: int = Field(default=10, ge=1)
    enable_proxy: bool = Field(default=False)
    enable_spoofing: bool = Field(default=False)
    randomize_intervals: bool = Field(default=True)
    custom_js: str = Field(default="", max_length=20000)

    @field_validator("custom_js")
    @classmethod
    def _js(cls, v: str) -> str:
        return v.strip()


class SessionCreate(BaseModel):
    """Create a session targeting a specific URL (e.g. a yo.fan page)."""

    url: str = Field(..., description="Target URL to generate views on.")
    name: str = Field(default="")
    config: AutomationConfig = Field(default_factory=AutomationConfig)

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            v = f"https://{v}"
        return v


class SessionStats(BaseModel):
    pages_loaded: int = 0
    scrolls_performed: int = 0
    tabs_switched: int = 0
    js_executions: int = 0
    errors: int = 0
    start_time: str | None = None
    last_active: str | None = None