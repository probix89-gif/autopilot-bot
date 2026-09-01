"""Stealth injection scripts — faithful port of the APK's W2.b logic.

The APK injects a JS bundle that:
  1. Overrides platform, userAgent, language, timezone.
  2. Adds deterministic canvas noise via a seeded PRNG (same seed →
     same noise → reproducible fingerprint per profile).
  3. Overrides WebGL vendor/renderer strings.
  4. (Optionally) overrides WebRTC behaviour.
This mirrors the exact approach seen in the decompiled source.
"""

from autopilot.domain.schemas import DeviceFingerprint
from autopilot.domain.enums import WebRtcPolicy


def build_stealth_js(fp: DeviceFingerprint) -> str:
    """Build the full stealth init-script for a tab's profile."""
    languages = ",".join(f"'{l}'" for l in fp.languages)
    webrtc_js = ""
    if fp.webrtc_policy == WebRtcPolicy.DISABLED:
        webrtc_js = "Object.defineProperty(RTCPeerConnection.prototype, 'localDescription', { get() { return null; } });"
    elif fp.webrtc_policy == WebRtcPolicy.PROXY_ONLY:
        webrtc_js = "const origCreate = RTCPeerConnection.prototype.createDataChannel; RTCPeerConnection.prototype.createDataChannel = function() { return null; };"

    return f"""
(function() {{
    const overrides = {{
        platform: '{fp.platform}',
        userAgent: '{fp.user_agent}',
        language: '{fp.locale}',
        languages: [{languages}],
        timezone: '{fp.timezone}',
    }};
    try {{
        Object.defineProperty(navigator, 'platform', {{ get: () => overrides.platform }});
        Object.defineProperty(navigator, 'userAgent', {{ get: () => overrides.userAgent }});
        Object.defineProperty(navigator, 'language', {{ get: () => overrides.language }});
        Object.defineProperty(navigator, 'languages', {{ get: () => overrides.languages }});
        Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {fp.cpu_cores} }});
        Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {fp.device_memory} }});
        Object.defineProperty(screen, 'width', {{ get: () => {fp.screen_width} }});
        Object.defineProperty(screen, 'height', {{ get: () => {fp.screen_height} }});
        Object.defineProperty(screen, 'pixelDepth', {{ get: () => {fp.screen_dpi} }});
        Object.defineProperty(screen, 'colorDepth', {{ get: () => {fp.screen_dpi} }});
    }} catch(e) {{}}

    // Deterministic canvas noise (seeded PRNG) — faithful to APK
    try {{
        const SEED = {fp.canvas_noise_seed};
        let s = SEED;
        function nextRand() {{ s = (s * 16807 + 7) % 2147483647; return s; }}

        const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        const origToBlob = HTMLCanvasElement.prototype.toBlob;
        const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;

        CanvasRenderingContext2D.prototype.getImageData = function() {{
            const imageData = origGetImageData.apply(this, arguments);
            const data = imageData.data;
            for (let i = 0; i < data.length; i += 4) {{
                data[i] = (data[i] + (nextRand() % 3) - 1) & 0xFF;
            }}
            return imageData;
        }};

        HTMLCanvasElement.prototype.toDataURL = function() {{
            const ctx = this.getContext('2d');
            if (ctx && this.width > 16 && this.height > 16) {{
                try {{
                    const imgData = origGetImageData.call(ctx, 0, 0,
                        Math.min(this.width, 100), Math.min(this.height, 100));
                    const d = imgData.data;
                    for (let i = 0; i < d.length; i += 4) {{
                        d[i] = (d[i] + (nextRand() % 3) - 1) & 0xFF;
                    }}
                    ctx.putImageData(imgData, 0, 0);
                }} catch(e) {{}}
            }}
            return origToDataURL.apply(this, arguments);
        }};
    }} catch(e) {{}}

    // WebGL vendor/renderer spoof
    try {{
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {{
            if (parameter === 37445) return '{fp.gl_vendor}';
            if (parameter === 37446) return '{fp.gl_renderer}';
            return getParameter.apply(this, arguments);
        }};
        if (WebGL2RenderingContext) {{
            const gp2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(parameter) {{
                if (parameter === 37445) return '{fp.gl_vendor}';
                if (parameter === 37446) return '{fp.gl_renderer}';
                return gp2.apply(this, arguments);
            }};
        }}
    }} catch(e) {{}}

    // WebRTC policy
    try {{ {webrtc_js} }} catch(e) {{}}
}})();
"""


class StealthInjector:
    """Injects stealth scripts into a Playwright context (APK's W2.b)."""

    async def apply(self, context, fp: DeviceFingerprint) -> None:
        js = build_stealth_js(fp)
        await context.add_init_script(js)