"""Local, accessible progress UI driven by completed work, never a timer."""
from base64 import b64encode
from html import escape
from math import ceil
from time import monotonic

import streamlit as st


FOX = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 62">
<style>
.leg {transform-box:fill-box;transform-origin:50% 0;animation:stride .45s ease-in-out infinite alternate}
.front {animation-direction:alternate-reverse}
@keyframes stride {from {transform:rotate(-18deg)} to {transform:rotate(18deg)}}
@media(prefers-reduced-motion:reduce) {.leg {animation:none}}
</style>
<path d="M38 36Q3 43 6 9Q18 27 41 23" fill="#e87533"/>
<path d="M6 9Q7 23 13 28L22 23Z" fill="#fff4df"/>
<ellipse cx="51" cy="34" rx="24" ry="15" fill="#f18437"/>
<path class="leg" d="M34 41L30 58H40L46 41" fill="#a54425"/>
<path class="leg front" d="M59 41L63 58H73L70 37" fill="#a54425"/>
<path d="M63 29L61 3L75 14L84 5L89 26L98 31L79 43L64 36Z" fill="#f18437"/>
<path d="M70 29L79 34L95 30L79 43Z" fill="#fff4df"/>
<path d="M65 10L67 22L72 16" fill="#a54425"/>
<circle cx="83" cy="25" r="2.5" fill="#18345b"/><circle cx="96" cy="31" r="3" fill="#18345b"/>
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
    .ep-track {{position:relative;height:12px;margin:58px 22px 12px;background:#dce6f5;border-radius:20px}}
    .ep-fill {{height:100%;width:{percent}%;background:#2563eb;border-radius:20px}}
    .ep-walker {{position:absolute;left:{percent}%;bottom:9px;width:62px;height:40px;transform:translateX(-50%)}}
    .ep-walker img {{width:62px;height:40px;animation:ep-walk .45s ease-in-out infinite alternate}}
    .ep-progress.done img,.ep-progress.failed img {{animation:none}}
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
    def __init__(self, label):
        self.slot = st.empty()
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
        self.slot.html(progress_html(self.value, label, timing, state))

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
            self.show(1, "Complete", f"Finished in {duration(monotonic() - self.started)}", force=True, state="done")
        else:
            self.show(self.value, "Processing stopped", "See the error below for details.", force=True, state="failed")
        return False
