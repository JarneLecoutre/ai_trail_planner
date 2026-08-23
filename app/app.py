import sys
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import streamlit.components.v1 as components

from app.app_utils import OUTPUT_DIR, map_path, run_planner


_executor = ThreadPoolExecutor(max_workers=2)

st.set_page_config(
    page_title="AI Trail Planner",
    page_icon="map",
    layout="wide",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Newsreader:opsz,wght@6..72,500;6..72,600&display=swap');

    :root {
        --ink: #24332c;
        --muted: #718078;
        --moss: #315c46;
        --moss-dark: #234536;
        --clay: #c77d55;
        --paper: #f6f4ee;
        --line: #dce2d8;
    }
    .stApp {
        background: var(--paper);
        color: var(--ink);
        font-family: 'DM Sans', sans-serif;
    }
    .stApp::before {
        content: '';
        position: fixed;
        inset: 0;
        pointer-events: none;
        opacity: .32;
        background-image: repeating-radial-gradient(ellipse at 15% 10%, transparent 0 24px, rgba(49,92,70,.07) 25px 26px, transparent 27px 52px);
        mask-image: linear-gradient(135deg, black, transparent 58%);
    }
    [data-testid='stHeader'] { background: transparent; }
    [data-testid='stAppViewContainer'] { background: transparent; }
    .block-container { max-width: 1180px; padding-top: 3.5rem; padding-bottom: 4rem; }
    .eyebrow {
        color: var(--clay); font-size: .74rem; font-weight: 700;
        letter-spacing: .12em; text-transform: uppercase; margin-bottom: .65rem;
    }
    .hero-title {
        color: var(--moss-dark); font-family: 'Newsreader', Georgia, serif;
        font-size: clamp(2.7rem, 5vw, 5.4rem); line-height: .95;
        margin: 0; max-width: 680px;
    }
    .hero-copy { color: var(--muted); font-size: 1.05rem; line-height: 1.6; max-width: 560px; margin-top: 1rem; }
    .prompt-label { color: var(--ink); font-size: .86rem; font-weight: 700; margin: 2.4rem 0 .35rem; }
    div[data-testid='stTextArea'] textarea {
        background: rgba(255,255,255,.78); border: 1px solid var(--line);
        border-radius: 10px; color: var(--ink); font-size: 1rem; line-height: 1.55;
        padding: 1rem 1.1rem; box-shadow: 0 12px 32px rgba(36,51,44,.06);
    }
    div[data-testid='stTextArea'] textarea:focus { border-color: var(--moss); box-shadow: 0 0 0 1px var(--moss); }
    div.stButton > button {
        background: var(--moss); border: 0; border-radius: 7px; color: white;
        font-weight: 700; min-height: 2.8rem; padding: 0 1.6rem;
        transition: background .2s ease, transform .2s ease;
    }
    div.stButton > button:hover { background: var(--moss-dark); transform: translateY(-1px); }
    .result-heading { border-top: 1px solid var(--line); margin-top: 3rem; padding-top: 1.5rem; }
    h2, h3 { color: var(--moss-dark); font-family: 'Newsreader', Georgia, serif; }
    [data-testid='stAlert'] { border-radius: 7px; }
    @media (max-width: 700px) {
        .block-container { padding-top: 2rem; }
        .hero-title { font-size: 3.2rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="eyebrow">Route intelligence · Kempen network</div>', unsafe_allow_html=True)
st.markdown('<h1 class="hero-title">A better walk starts with a good description.</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="hero-copy">Tell the planner where you want to go, how far you want to walk, and what the path should feel like. It will translate your words into a route.</p>',
    unsafe_allow_html=True,
)


def show_map(path):
    if not path.exists():
        st.warning("The route was accepted, but the map file was not found.")
        return
    components.html(path.read_text(encoding="utf-8"), height=650, scrolling=False)


prompt_column, _ = st.columns([1.35, .65])
with prompt_column:
    st.markdown('<div class="prompt-label">Your trail brief</div>', unsafe_allow_html=True)
    user_request = st.text_area(
        "Describe your trail",
        height=150,
        label_visibility="collapsed",
        placeholder=(
            "Create a 10 km loop from Grobbendonk through open green spaces."
        ),
    )
    plan_clicked = st.button("Plan my trail", type="primary")

if plan_clicked:
    request = user_request.strip()
    if not request:
        st.warning("Please describe the trail you want before planning it.")
        st.stop()

    map_name = f"streamlit_trail_{uuid.uuid4().hex}.html"
    OUTPUT_DIR.mkdir(exist_ok=True)
    st.session_state["planner_future"] = _executor.submit(
        run_planner,
        request,
        {
            "start_lat": None,
            "start_lon": None,
            "end_lat": None,
            "end_lon": None,
        },
        map_name,
    )
    st.session_state["planner_request"] = request
    st.session_state["planner_map_name"] = map_name
    st.session_state.pop("planner_result", None)
    st.session_state.pop("planner_error", None)

future: Future | None = st.session_state.get("planner_future")
if future is not None and not future.done():
    st.info("The trail planner is working in the background. This page will update when it is finished.")
    time.sleep(0.5)
    st.rerun()

if future is not None and future.done() and "planner_result" not in st.session_state and "planner_error" not in st.session_state:
    try:
        st.session_state["planner_result"] = future.result()
    except Exception as error:
        st.session_state["planner_error"] = str(error)

if st.session_state.get("planner_error"):
    st.error("The trail planner could not complete: " + st.session_state["planner_error"])

result = st.session_state.get("planner_result")
if result:
    route_request = result.get("route_request") or {}
    st.markdown('<div class="result-heading"></div>', unsafe_allow_html=True)
    st.success("Trail created.")
    left, right = st.columns([2, 1])
    with left:
        show_map(map_path(st.session_state["planner_map_name"]))
    with right:
        st.subheader("Planner summary")
        if result.get("final_narrative"):
            st.write(result["final_narrative"])
        st.subheader("What it understood")
        st.json(route_request)
        st.caption("Request sent to the planner")
        st.write(st.session_state.get("planner_request", ""))
