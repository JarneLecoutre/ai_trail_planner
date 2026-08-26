# AI Trail Planner

AI Trail Planner is a multi-agent hiking route assistant with a Streamlit user interface.
It converts natural language route requests into structured intent, enriches them with
weather context, computes graph-based route candidates in Neo4j, validates the result,
and returns an interactive map plus optional GPX export.

## What the app does

- Accepts free-form trail requests in plain English.
- Extracts route intent:
	- Route type (loop or point-to-point)
	- Optional target distance
	- Start, end, and optional pass-through location
	- Environmental and accessibility preferences
- Uses weather forecasts (Open-Meteo) for route-day context.
- Generates route candidates on an OSM-like network stored in Neo4j.
- Applies preference-aware edge weighting (green, paved/unpaved, wheelchair, etc.).
- Validates output and renders a Folium HTML map.
- Allows GPX download from route geometry.

## Project structure

- agents/: Multi-agent graph nodes and orchestration logic.
- app/: Streamlit application and app-level utilities.
- services/: Infrastructure adapters (Neo4j and weather API).
- utils/: Output helpers (map rendering, GPX generation).
- output/: Generated route maps.
- scratch/: Experimental and data preparation notebooks/scripts.

## Architecture overview

The LangGraph workflow is:

1. intent: Parse user request into structured route intent.
2. weather: Fetch and apply weather-aware preference enrichment.
3. orchestrator: Compute dynamic routing constraints.
4. router: Build route candidates with preference-weighted costs.
5. validator: Validate and render route map output.
6. orchestrator (final pass): Produce user-facing route narrative.

The workflow retries invalid route attempts up to a bounded limit.

## Prerequisites

- Python 3.11+ recommended.
- Access to a Neo4j database containing OSMNode nodes and CONNECTED_TO edges.
- Google Generative AI access for LLM calls.

## Environment variables

Create a .env file in the repository root with:

```env
NEO4j_URI=...
NEO4j_USERNAME=...
NEO4j_PASSWORD=...
NEO4j_DATABASE=neo4j
GCP_PROJECT_ID=...
GCP_LOCATION=...
```

## Install and run

Use your preferred dependency management workflow, then run:

```powershell
streamlit run app/app.py
```

For a single CLI execution (without Streamlit):

```powershell
python main.py
```

## Core behavior details

- Routing uses weighted temporary edge costs based on extracted preferences.
- Loop routes try to avoid reusing the same road segments on the return leg.
- Point-to-point routes may include a mandatory pass-through location.
- Weather enrichment can promote paved paths when mud avoidance is requested.
- Map generation prefers stored edge geometry and falls back to node-to-node lines.

## Outputs

- HTML map files are written to output/.
- Streamlit embeds the map directly in the app.
- GPX is generated on demand when enough route coordinates are available.
