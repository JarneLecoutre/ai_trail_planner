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
from utils.gpx_generator import extract_coordinates_for_gpx, generate_gpx


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
        --sun: #e8ad45;
        --sky: #e5f0ef;
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
    .block-container { max-width: 1220px; padding-top: 2.4rem; padding-bottom: 4rem; }
    .eyebrow {
        color: var(--clay); font-size: .74rem; font-weight: 700;
        letter-spacing: .12em; text-transform: uppercase; margin-bottom: .65rem;
    }
    .hero-title {
        color: var(--moss-dark); font-family: 'Newsreader', Georgia, serif;
        font-size: clamp(2.7rem, 5vw, 5.4rem); line-height: .95;
        margin: 0; max-width: 760px;
    }
    .hero-copy { color: var(--muted); font-size: 1.05rem; line-height: 1.6; max-width: 620px; margin-top: 1rem; }
    .prompt-label { color: var(--ink); font-size: .86rem; font-weight: 700; margin: 2rem 0 .35rem; }
    .section-kicker { color: var(--clay); font-size: .72rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; margin-bottom: .35rem; }
    .weather-strip { background: var(--sky); border-left: 4px solid var(--sun); padding: 1rem 1.2rem; margin: 1.2rem 0; }
    .weather-strip strong { color: var(--moss-dark); }
    .advice-list { background: rgba(255,255,255,.68); border: 1px solid var(--line); padding: 1rem 1.2rem; }
    .advice-item { color: var(--ink); line-height: 1.45; margin: .55rem 0; }
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
    div[data-testid='stMetric'] { background: rgba(255,255,255,.6); border: 1px solid var(--line); padding: .8rem; }
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


future: Future | None = st.session_state.get("planner_future")
is_planning = future is not None and not future.done()

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
    plan_clicked = st.button("Plan my trail", type="primary", disabled=is_planning)

if plan_clicked:
    request = user_request.strip()
    if not request:
        st.warning("Please describe the trail you want before planning it.")
        st.stop()

    for key in ("planner_future", "planner_request", "planner_map_name", "planner_result", "planner_error"):
        st.session_state.pop(key, None)

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
    st.rerun()

if future is not None and not future.done():
    with st.spinner("Planning your trail..."):
        time.sleep(0.5)
        st.rerun()

if future is not None and future.done():
    try:
        st.session_state["planner_result"] = future.result()
        st.session_state.pop("planner_error", None)
    except Exception as error:
        st.session_state.pop("planner_result", None)
        st.session_state["planner_error"] = str(error)
    st.session_state.pop("planner_future", None)
    st.rerun()

if not is_planning and st.session_state.get("planner_error"):
    print("[Planner] The trail planner could not complete: " + st.session_state["planner_error"])

result = st.session_state.get("planner_result")
if result:
    route_request = result.get("route_request") or {}
    st.markdown('<div class="result-heading"></div>', unsafe_allow_html=True)
    st.success("Trail created and ready to explore.")
    weather = result.get("weather_report") or {}
    raw_route = result.get("raw_route_data") or [{}]
    actual_km = (raw_route[0].get("totalDistance", 0) or 0) / 1000
    st.markdown('<div class="section-kicker">Your trail brief</div>', unsafe_allow_html=True)
    metric_columns = st.columns(4)
    metric_columns[0].metric("Route", route_request.get("route_type", "loop").replace("_", " ").title())
    metric_columns[1].metric("Distance", f"{actual_km:.1f} km")
    metric_columns[2].metric("Forecast", str(weather.get("date", "Unavailable")))
    metric_columns[3].metric("High", f"{weather.get('temperature_max_c', '--')} C")
    if weather:
        st.markdown(
            f'<div class="weather-strip"><strong>Trail conditions</strong><br>'
            f'Rain: {weather.get("rain_mm", 0)} mm · Chance: {weather.get("precipitation_probability", "--")}% · '
            f'Wind: {weather.get("wind_speed_max_kmh", "--")} km/h</div>',
            unsafe_allow_html=True,
        )
        if weather.get("route_guidance"):
            st.info(weather["route_guidance"])
    left, right = st.columns([1.7, 1])
    with left:
        show_map(map_path(st.session_state["planner_map_name"]))
    with right:
        st.markdown('<div class="section-kicker">Trail notes</div>', unsafe_allow_html=True)
        if result.get("final_narrative"):
            st.write(result["final_narrative"])
        route_coordinates = extract_coordinates_for_gpx(raw_route)
        if len(route_coordinates) >= 2:
            gpx_data = generate_gpx(
                route_coordinates,
                route_name="AI Trail Planner Route",
                route_description=st.session_state.get("planner_request", ""),
                distance_km=actual_km,
            )
            st.download_button(
                "Download GPX",
                data=gpx_data,
                file_name="ai-trail-planner-route.gpx",
                mime="application/gpx+xml",
            )
        else:
            st.warning("GPX download is unavailable because the route has too few coordinates.")
        st.markdown('<div class="section-kicker">What to wear</div>', unsafe_allow_html=True)
        advice = weather.get("clothing_advice")
        if advice:
            st.markdown('<div class="advice-list">' + ''.join(f'<div class="advice-item">• {item}</div>' for item in advice) + '</div>', unsafe_allow_html=True)
        with st.expander("Show route details"):
            st.json(route_request)
