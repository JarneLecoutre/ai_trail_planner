from datetime import date, timedelta
import json
from typing import Any, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from langchain_core.tools import tool


OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def get_forecast(latitude: float, longitude: float, forecast_date: Optional[str] = None) -> dict[str, Any]:
	"""Fetch one day's weather from Open-Meteo for a route coordinate."""
	requested_date = date.fromisoformat(forecast_date) if forecast_date else date.today()
	if requested_date < date.today() or requested_date > date.today() + timedelta(days=15):
		raise ValueError("Weather forecasts are only available from today through the next 15 days.")

	query = urlencode({
		"latitude": latitude,
		"longitude": longitude,
		"daily": "weather_code,temperature_2m_max,wind_speed_10m_max,precipitation_probability_max,rain_sum,showers_sum,snowfall_sum",
		"timezone": "auto",
		"start_date": requested_date.isoformat(),
		"end_date": requested_date.isoformat(),
	})
	request = Request(f"{OPEN_METEO_FORECAST_URL}?{query}", headers={"User-Agent": "AI-Trail-Planner/1.0"})
	with urlopen(request, timeout=8) as response:
		payload = json.load(response)

	daily = payload.get("daily") or {}
	return {
		"date": requested_date.isoformat(),
		"weather_code": (daily.get("weather_code") or [None])[0],
		"temperature_max_c": (daily.get("temperature_2m_max") or [None])[0],
		"wind_speed_max_kmh": (daily.get("wind_speed_10m_max") or [0])[0] or 0,
		"precipitation_probability": (daily.get("precipitation_probability_max") or [None])[0],
		"rain_mm": (daily.get("rain_sum") or [0])[0] or 0,
		"showers_mm": (daily.get("showers_sum") or [0])[0] or 0,
		"snowfall_cm": (daily.get("snowfall_sum") or [0])[0] or 0,
	}


@tool
def weather_lookup_tool(latitude: float, longitude: float, forecast_date: Optional[str] = None) -> dict[str, Any]:
	"""Look up the daily forecast for a hiking location and date."""
	return get_forecast(latitude, longitude, forecast_date)
