from typing import Any

def orchestrator_node(state: dict) -> dict:
    if state.get("is_valid"):
        print("[Orchestrator Node] Route structure passed validation. Compiling user summary...")
        llm = state["_llm"]
        route_request = state.get("route_request") or {}
        route_type = route_request.get("route_type", "loop")
        map_output_name = state.get("map_output_name", "route_map.html")

        raw_route = state.get("raw_route_data") or [{}]
        total_m = raw_route[0].get("totalDistance", 0) if isinstance(raw_route, list) and raw_route else 0
        actual_km = round(total_m / 1000, 2)
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
        Context: The route map has been successfully computed and saved to 'output/{map_output_name}'.
        Requested route type: {route_type}
        Requested distance: {requested_km} km
        Actual calculated route distance: {actual_km} km
        {weather_context}

        Task: Write a short, engaging, and friendly English summary welcoming the hiker. Include the route type, estimated distance, weather forecast, and mention that the interactive map is generated and ready to open.
        """
        ai_message = llm.invoke(prompt)
        return {"final_narrative": ai_message.content}
        
    print("[Orchestrator Node] Calculating mathematical GIS thresholds...")
    route_request = state.get("route_request") or {}
    
    # Safe fallback lookup using .get() for distance_km
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