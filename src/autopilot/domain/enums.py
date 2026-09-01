"""Domain enums mirroring the AutoPilot APK exactly."""

from enum import Enum


class AutomationMode(str, Enum):
    SIMPLE_SCROLL = "simple_scroll"
    DEEP_SCROLL = "deep_scroll"
    TAB_SWITCHING = "tab_switching"
    CUSTOM_JS = "custom_js"

    @property
    def label(self) -> str:
        return {
            AutomationMode.SIMPLE_SCROLL: "Simple Scroll + Refresh",
            AutomationMode.DEEP_SCROLL: "Deep Scroll",
            AutomationMode.TAB_SWITCHING: "Tab Switching",
            AutomationMode.CUSTOM_JS: "Custom JavaScript",
        }[self]


class SessionStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class ProxyProtocol(str, Enum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS4 = "socks4"
    SOCKS5 = "socks5"


class WebRtcPolicy(str, Enum):
    DEFAULT = "default"
    DISABLED = "disabled"
    PROXY_ONLY = "proxy_only"


class CommandType(str, Enum):
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    ADD_TAB = "add_tab"
    REMOVE_TAB = "remove_tab"