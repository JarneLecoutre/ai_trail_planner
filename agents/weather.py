from datetime import date

from services.weather_service import get_forecast


def weather_node(state: dict) -> dict:
    """Use the parsed route position and date to enrich weather-sensitive intent."""
    route_request = state.get("route_request") or {}
    start_point = route_request.get("start_point")
    if not start_point:
        return {"weather_report": None, "weather_error": "Weather check skipped: no route position."}

    forecast_date = route_request.get("hike_date") or date.today().isoformat()
    try:
        report = get_forecast(start_point[0], start_point[1], forecast_date)
    except Exception as error:
        print(f"[Weather Agent] Forecast unavailable: {error}")
        return {"weather_report": None, "weather_error": str(error)}

    wet = report["rain_mm"] > 0 or report["showers_mm"] > 0
    preferences = dict(route_request.get("environmental_preferences") or {})
    if wet and preferences.get("avoid_mud"):
        preferences["avoid_unpaved"] = True

    enriched_request = dict(route_request)
    enriched_request["environmental_preferences"] = preferences
    return {"route_request": enriched_request, "weather_report": report, "weather_error": None}