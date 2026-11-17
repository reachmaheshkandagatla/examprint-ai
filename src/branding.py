"""Local vector branding and navigation for the ExamPrint workspace."""
from base64 import b64encode
from pathlib import Path
import streamlit as st

ASSETS = Path(__file__).resolve().parents[1] / "assets"
BANNERS = (
    ("upload", "01 · Upload & Configure", "Your lecture, ready to arrange.",
     "Upload a PDF, choose slides per side, and adjust the paper layout for your handout."),
    ("preview", "02 · Print Preview", "Check every detail before printing.",
     "Generate a three-side preview. Browse your slides and zoom in to check spacing and readability."),
    ("index", "03 · Editable Topic Index", "Give every topic its place.",
     "Choose an index source, review topic names and page references, then select what to include."),
    ("export", "04 · Export", "All sorted. Ready to print.",
     "Generate and download your handout, separate topic index, or both PDFs in a ZIP. Keep both PDFs together for index links."),
)


def go_home():
    """Return to the first tab without clearing the uploaded PDF or edits."""
    st.session_state.workflow_tab = "Upload & Configure"


def render_brand_header():
    logo_uri = "data:image/svg+xml;base64," + b64encode((ASSETS / "examprint-fox.svg").read_bytes()).decode()
    st.html('''<style>
    .st-key-fox_home button {
        width: 88px; max-width: 100%; height: 88px; border: 1px solid transparent;
        border-radius: 18px; background-color: transparent;
        background-image: url("''' + logo_uri + '''");
        background-size: contain; background-position: center; background-repeat: no-repeat;
        transition: transform .15s ease, background-color .15s ease;
    }
    .st-key-fox_home button p {
        position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
        overflow: hidden; clip-path: inset(50%); white-space: nowrap;
    }
    .st-key-fox_home button:hover { background-color: #edf4ff; transform: translateY(-2px); border-color: #a8c8f5; }
    .st-key-fox_home button:focus-visible { outline: 3px solid #2563eb; outline-offset: 3px; }
    @media (prefers-reduced-motion: reduce) { .st-key-fox_home button { transition: none; } }
    </style>''')
    logo, title = st.columns([1, 10], vertical_alignment="center")
    with logo:
        st.button("Home — Upload & Configure", key="fox_home", on_click=go_home)
    with title:
        st.title("ExamPrint AI")


def render_tab_banner(index):
    name, step, heading, description = BANNERS[index]
    # st.html uses an HTML-only sanitizer, which removes inline <svg> nodes.
    # An image data URI preserves our local vector artwork through sanitization.
    illustration_uri = "data:image/svg+xml;base64," + b64encode((ASSETS / f"fox-{name}.svg").read_bytes()).decode()
    st.html('''
    <style>
    .ep-banner {
        display: flex; align-items: center; justify-content: space-between; gap: 24px;
        padding: 16px 24px 16px 32px; margin: 12px 0 20px;
        border: 1px solid #dce6f5; border-radius: 22px;
        background: linear-gradient(115deg, #f8fbff 0%, #f0f6ff 65%, #fff5e9 100%);
        color: #18345b;
    }
    .ep-banner-copy { flex: 1; min-width: 0; }
    .ep-banner .ep-eyebrow { font-size: 11px; font-weight: 700; letter-spacing: 1.5px;
        text-transform: uppercase; color: #45658e; margin: 0 0 12px; }
    .ep-banner h2 { color: #18345b; font-size: clamp(22px, 2.8vw, 32px);
        line-height: 1.2; letter-spacing: -.6px; padding: 0; margin: 0 0 12px; }
    .ep-banner p { color: #456080; max-width: 600px; font-size: 15px; line-height: 1.6; margin: 0; }
    .ep-banner-art { flex: 0 0 250px; margin-left: auto; }
    .ep-banner-art img { display: block; width: 100%; height: auto; }
    @media (max-width: 640px) {
        .ep-banner { gap: 10px; padding: 20px 16px; flex-wrap: wrap; }
        .ep-banner-copy { flex-basis: 220px; }
        .ep-banner-art { flex-basis: 150px; }
    }
    </style>
    <section class="ep-banner" aria-label="''' + step + '''">
      <div class="ep-banner-copy">
        <p class="ep-eyebrow">''' + step + '''</p>
        <h2>''' + heading + '''</h2>
        <p>''' + description + '''</p>
      </div>
      <div class="ep-banner-art"><img src="''' + illustration_uri + '''"
        alt="Fox helping with ''' + name + '''" width="350" height="220"></div>
    </section>
    ''')
