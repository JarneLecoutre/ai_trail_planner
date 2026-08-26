"""Utility helpers shared by the Streamlit app."""

import os
import agents.routing as routing_module
from pathlib import Path

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from agents.graph_builder import compiled_agent_graph
from services.neo4j_service import Neo4jService


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"


def _close_neo4j_service(service) -> None:
    """Close Neo4j connections for both service implementations used in this project."""
    if service is None:
        return
    if hasattr(service, "close"):
        service.close()
    elif hasattr(service, "graph") and hasattr(service.graph, "_driver"):
        service.graph._driver.close()


def run_planner(request, coordinates, map_name):
    """Run one planner execution and return the final graph state."""
    load_dotenv(PROJECT_ROOT / ".env")
    print(f"[Planner] Loaded routing module from: {routing_module.__file__}")
    service = None
    try:
        service = Neo4jService(
            uri=os.getenv("NEO4j_URI"),
            username=os.getenv("NEO4j_USERNAME"),
            password=os.getenv("NEO4j_PASSWORD"),
            database=os.getenv("NEO4j_DATABASE", "neo4j"),
        )
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            project=os.getenv("GCP_PROJECT_ID"),
            location=os.getenv("GCP_LOCATION"),
            temperature=0.1,
        )
        state = {
            "user_request": request,
            "map_output_name": map_name,
            "map_output_path": str(OUTPUT_DIR / map_name),
            "start_lat": coordinates["start_lat"],
            "start_lon": coordinates["start_lon"],
            "end_lat": coordinates["end_lat"],
            "end_lon": coordinates["end_lon"],
            "retry_count": 0,
            "is_valid": False,
            "raw_route_data": None,
            "final_narrative": None,
            "_llm": llm,
            "_graph_service": service,
        }
        return compiled_agent_graph.invoke(state)
    finally:
        _close_neo4j_service(service)


def map_path(map_name):
    """Return the absolute path of a generated map inside the output folder."""
    return OUTPUT_DIR / map_name
