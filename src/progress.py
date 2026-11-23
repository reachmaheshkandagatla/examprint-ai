"""Local, accessible progress UI driven by completed work, never a timer."""
from base64 import b64encode
from html import escape
from math import ceil
from time import monotonic

import streamlit as st


FOX = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 90">
<style>
.leg {transform-box:fill-box;transform-origin:50% 0;animation:stride .6s ease-in-out infinite alternate}
.front {animation-direction:alternate-reverse}
@keyframes stride {from {transform:rotate(-12deg)} to {transform:rotate(12deg)}}
@media(prefers-reduced-motion:reduce) {.leg {animation:none}}
</style>
<!-- Folded tail, with a cream paper tip. -->
<path d="M48 58 17 60 3 24 30 40 48 43Z" fill="#e7793d"/>
<path d="M3 24 30 40 17 60Z" fill="#ffad67"/>
<path d="M3 24 10 43 20 39Z" fill="#fff6e7"/>
<path d="M17 60 30 40 48 58Z" fill="#c95b32"/>
<!-- Small folded body and alternating paper paws. -->
<path class="leg" d="M45 62 40 82 52 82 57 61Z" fill="#b95732"/>
<path class="leg front" d="M69 61 70 82 82 82 79 57Z" fill="#dd743d"/>
<path d="M42 42 72 37 85 64 61 74 37 63Z" fill="#ef8846"/>
<path d="M42 42 61 74 37 63Z" fill="#ffbd79"/>
<path d="M72 37 61 74 85 64Z" fill="#d66b36"/>
<path d="M72 45 61 66 78 62Z" fill="#fff2dc"/>
<!-- Oversized origami head, little ears and a friendly face. -->
<path d="M56 12 75 23 91 21 109 8 105 41 85 58 62 44Z" fill="#f8954e"/>
<path d="M56 12 75 23 62 44Z" fill="#d96e38"/>
<path d="M109 8 91 21 105 41Z" fill="#e47c3c"/>
<path d="M61 20 65 34 71 25Z M103 17 95 25 102 32Z" fill="#fff1dc"/>
<path d="M75 23 85 49 91 21Z" fill="#ffbb71"/>
<path d="M62 39 75 35 85 49 98 34 105 41 85 58Z" fill="#fff8eb"/>
<path d="M85 49 85 58 105 41Z" fill="#f2dfc8"/>
<path d="m71 36 4 2m19-2 4-2" stroke="#493627" stroke-width="2.7" stroke-linecap="round"/>
<path d="m81 47 8 0-4 5Z" fill="#493627"/>
<ellipse cx="72" cy="43" rx="3" ry="1.6" fill="#f7b79a"/>
<ellipse cx="97" cy="41" rx="3" ry="1.6" fill="#f7b79a"/>
</svg>'''
FOX_URI = 'data:image/svg+xml;base64,' + b64encode(FOX.encode()).decode()
STILL_FOX_URI = 'data:image/svg+xml;base64,' + b64encode(FOX.replace('class="leg"', '').replace('class="leg front"', '').encode()).decode()


def duration(seconds):
    seconds = max(1, ceil(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes = ceil(seconds / 60)
    return f"{minutes} min" if minutes < 60 else f"{minutes // 60}h {minutes % 60} min"


def progress_html(value, text, timing, state="running"):
    percent = min(100, max(0, int(value * 100)))
    fox_uri = FOX_URI if state == "running" else STILL_FOX_URI
    return f'''<style>
    .ep-progress {{padding:18px 24px;border:1px solid #c5d9f5;border-radius:18px;
      background:#f5f9ff;color:#18345b;margin:12px 0}}
    .ep-progress-head {{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}}
    .ep-track {{position:relative;height:12px;margin:80px 24px 12px;background:#dce6f5;border-radius:20px}}
    .ep-fill {{height:100%;width:{percent}%;background:#2563eb;border-radius:20px}}
    .ep-walker {{position:absolute;left:{percent}%;bottom:9px;width:88px;height:66px;transform:translateX(-50%)}}
    .ep-walker img {{width:88px;height:66px;animation:ep-walk .45s ease-in-out infinite alternate}}
    .ep-progress.done img,.ep-progress.failed img,.ep-progress.idle img {{animation:none}}
    .ep-progress small {{color:#456080}}
    @keyframes ep-walk {{from {{transform:translateY(0) rotate(-3deg)}} to {{transform:translateY(-4px) rotate(3deg)}}}}
    @media(prefers-reduced-motion:reduce) {{.ep-walker img {{animation:none}}}}
    </style><section class="ep-progress {state}" aria-label="Document processing">
    <div class="ep-progress-head"><strong>{escape(text)}</strong><span>{percent}%</span></div>
    <div class="ep-track" role="progressbar" aria-label="Document processing" aria-valuemin="0"
      aria-valuemax="100" aria-valuenow="{percent}" aria-valuetext="{escape(text, quote=True)}">
      <div class="ep-fill"></div><div class="ep-walker"><img src="{fox_uri}" alt=""/></div></div>
    <div class="ep-progress-head"><small>{escape(timing)}</small><small>Completed ← · → Remaining</small></div>
    </section>'''


class FoxProgress:
    def __init__(self, label, slots=None, on_update=None):
        self.slots = slots if slots is not None else [st.empty()]
        self.on_update = on_update
        self.operation = label.rstrip(".…")
        self.started = monotonic()
        self.last_render = 0
        self.value = 0
        self.label = label
        self.show(0, label, "ETA: Estimating…", force=True)

    def show(self, value, label, timing="ETA: Estimating…", *, force=False, state="running"):
        self.value = max(self.value, min(value, .99 if state == "running" else 1))
        self.label = label
        now = monotonic()
        if not force and now - self.last_render < .15:
            return
        self.last_render = now
        markup = progress_html(self.value, label, timing, state)
        for slot in self.slots:
            slot.html(markup)
        if self.on_update:
            self.on_update(markup)

    def stage(self, label, start, end):
        """Return a fraction callback; ETA is scoped to this measurable step."""
        began = monotonic()
        self.show(start, label, force=True)

        def update(fraction):
            fraction = min(1, max(0, fraction))
            elapsed = monotonic() - began
            eta = (f"Estimated time left in this step: {duration(elapsed * (1 - fraction) / fraction)}"
                   if 0 < fraction < 1 and elapsed >= 1 else "ETA: Estimating…")
            self.show(start + (end - start) * fraction, label, eta, force=fraction == 1)
        return update

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        if kind is None:
            self.show(1, f"Complete · {self.operation}", f"Finished in {duration(monotonic() - self.started)}", force=True, state="done")
        else:
            self.show(self.value, "Processing stopped", "See the error below for details.", force=True, state="failed")
        return False
