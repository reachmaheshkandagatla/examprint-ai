"""Local vector branding for the ExamPrint workspace."""
from pathlib import Path
import streamlit as st

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def render_brand_header():
    logo, title = st.columns([1, 10], vertical_alignment="center")
    with logo:
        st.image(str(ASSETS / "examprint-fox.svg"), width=88)
    with title:
        st.title("ExamPrint AI")
        st.caption("Offline lecture handouts · Separate, editable topic index · Duplex-ready A4")


def render_upload_intro():
    illustration = (ASSETS / "fox-print-studio.svg").read_text(encoding="utf-8")
    st.html('''
    <style>
    .ep-welcome {
        display: flex; align-items: center; gap: 24px;
        padding: 24px 36px; margin: 12px 0 20px;
        border: 1px solid #dce6f5; border-radius: 22px;
        background: linear-gradient(115deg, #f8fbff 0%, #f0f6ff 65%, #fff5e9 100%);
        color: #18345b;
    }
    .ep-welcome-copy { flex: 1; }
    .ep-welcome .ep-eyebrow {
        font-size: 11px; font-weight: 700; letter-spacing: 2px;
        text-transform: uppercase; color: #45658e; margin: 0 0 12px;
    }
    .ep-welcome h2 { color: #18345b; font-size: clamp(24px, 3vw, 36px);
        line-height: 1.18; letter-spacing: -.8px; padding: 0; margin: 0 0 14px; }
    .ep-welcome p { color: #456080; max-width: 440px; font-size: 15px; line-height: 1.65; }
    .ep-welcome .ep-steps { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 20px; }
    .ep-welcome .ep-step { border: 1px solid #d9e5f5; border-radius: 20px;
        background: #ffffffb8; padding: 6px 12px; font-size: 12px; color: #31547e; }
    .ep-welcome .ep-step b { color: #2563eb; margin-right: 5px; }
    .ep-welcome-art { flex: 1; max-width: 460px; min-width: 0; }
    .ep-welcome-art svg { display: block; width: 100%; height: auto; }
    @media (max-width: 640px) {
        .ep-welcome { flex-direction: column; gap: 4px; padding: 24px; }
        .ep-welcome-art { width: 100%; max-width: 300px; }
    }
    </style>
    <section class="ep-welcome" aria-label="Prepare your study handout">
      <div class="ep-welcome-copy">
        <p class="ep-eyebrow">A little order. A lot less paper.</p>
        <h2>Big lectures.<br>Neat little handouts.</h2>
        <p>Give your slides a tidy home. Upload a lecture PDF, arrange your pages,
        and build an index that helps you find every topic.</p>
        <div class="ep-steps" aria-label="Your workflow">
          <span class="ep-step"><b>01</b> Upload</span>
          <span class="ep-step"><b>02</b> Arrange</span>
          <span class="ep-step"><b>03</b> Print</span>
        </div>
      </div>
      <div class="ep-welcome-art">''' + illustration + '''</div>
    </section>
    ''')
