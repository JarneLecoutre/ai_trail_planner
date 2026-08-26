"""Orchestrator node that computes thresholds and drafts the final user narrative."""

from typing import Any


UNPAVED_SURFACES = {"unpaved", "dirt", "gravel", "ground", "compacted"}
PAVED_SURFACES = {"paved", "asphalt", "concrete", "paving_stones"}
GREEN_HIGHWAYS = {"path", "track", "bridleway"}


def _is_yes(value: Any) -> bool:
    """Return True for boolean-like yes/true values used in graph properties."""
    return value is True or str(value).lower() in {"yes", "true"}


def _route_surface_totals(raw_route: list) -> dict[str, float]:
    """Aggregate paved/unpaved/green distances in kilometers from edge metadata."""
    edges = raw_route[0].get("edge_details", []) if raw_route else []
    totals = {"paved": 0.0, "unpaved": 0.0, "green": 0.0}

    for edge in edges:
        distance_m = float(edge.get("distance") or 0)
        surface = str(edge.get("surface") or "").lower()
        is_unpaved = _is_yes(edge.get("is_unpaved")) or surface in UNPAVED_SURFACES
        is_green = (
            _is_yes(edge.get("is_green"))
            or _is_yes(edge.get("is_forest"))
            or _is_yes(edge.get("is_park"))
            or _is_yes(edge.get("is_nature_reserve"))
            or _is_yes(edge.get("is_open_green"))
            or str(edge.get("highway") or "").lower() in GREEN_HIGHWAYS
        )

        if is_unpaved:
            totals["unpaved"] += distance_m
        elif surface in PAVED_SURFACES:
            totals["paved"] += distance_m
        if is_green:
            totals["green"] += distance_m

    return {name: round(distance / 1000, 2) for name, distance in totals.items()}


def orchestrator_node(state: dict) -> dict:
    """Either build constraints for routing retries or produce the final narrative."""
    if state.get("is_valid"):
        print("[Orchestrator Node] Route structure passed validation. Compiling user summary...")
        llm = state["_llm"]
        route_request = state.get("route_request") or {}
        route_type = route_request.get("route_type", "loop")

        raw_route = state.get("raw_route_data") or [{}]
        total_m = raw_route[0].get("totalDistance", 0) if isinstance(raw_route, list) and raw_route else 0
        actual_km = round(total_m / 1000, 2)
        surface_totals = _route_surface_totals(raw_route)
        requested_km = route_request.get("distance_km", state.get("distance_km", 5.0))
        weather_report = state.get("weather_report")
        weather_context = "No weather report was available."
        if weather_report:
            weather_context = (
                f"Forecast for {weather_report['date']}: precipitation probability "
                f"{weather_report['precipitation_probability']}%, rain "
                f"{weather_report['rain_mm']} mm, showers {weather_report['showers_mm']} mm, "
                f"snowfall {weather_report['snowfall_cm']} cm, maximum temperature "
                f"{weather_report.get('temperature_max_c', 'unknown')} C."
            )

        prompt = f"""
        Role: Professional Trail Guide Expert
        Requested route type: {route_type}
        Requested distance: {requested_km} km
        Actual calculated route distance: {actual_km} km
        Paved distance: {surface_totals['paved']} km
        Unpaved distance: {surface_totals['unpaved']} km
        Green distance: {surface_totals['green']} km
        {weather_context}

        Task: Write a short, engaging, and friendly English summary welcoming the hiker. Include the route type, estimated distance, weather forecast, and the paved, unpaved, and green distance totals.
        """
        ai_message = llm.invoke(prompt)
        return {"final_narrative": ai_message.content}
        
    print("[Orchestrator Node] Calculating mathematical GIS thresholds...")
    route_request = state.get("route_request") or {}
    
    # Safe fallback lookup for distance_km.
    effective_distance = route_request.get("distance_km") or state.get("distance_km") or 5.0
    target_dist = float(effective_distance) * 1000.0
    multiplier = 1.0 + (state.get("retry_count", 0) * 0.15)
    
    constraints = {
        "min_beeline": target_dist * 0.25,
        "max_beeline": target_dist * 0.42 * multiplier,
        "min_total": target_dist * 0.82,
        "max_total": target_dist * 1.18 * multiplier
    }
    return {"constraints": constraints, "retry_count": state.get("retry_count", 0)}