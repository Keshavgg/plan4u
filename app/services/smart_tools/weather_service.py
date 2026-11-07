"""Destination weather and golden-hour insights from Open-Meteo (no API key required)."""
import datetime
import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 8

# WMO weather interpretation codes (https://open-meteo.com/en/docs).
WMO_CONDITIONS = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


def _get_json(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full_url, headers={"User-Agent": "Plan4U-App/1.0"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fmt_time(dt: datetime.datetime) -> str:
    return dt.strftime("%I:%M %p")


def get_destination_weather_insights(
    city: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> Dict[str, Any]:
    """Returns a 7-day forecast plus sunrise/sunset and golden-hour windows for a city.

    Golden hours are computed from the actual sunrise/sunset times. Coordinates are
    resolved from the city name via Open-Meteo geocoding unless lat/lng are given.
    """
    try:
        if lat is None or lng is None:
            geo = _get_json(GEOCODE_URL, {"name": city, "count": 1, "language": "en", "format": "json"})
            results = geo.get("results") or []
            if not results:
                return {"success": False, "city": city.title(), "error": f"Could not locate '{city}'."}
            lat, lng = results[0]["latitude"], results[0]["longitude"]

        data = _get_json(FORECAST_URL, {
            "latitude": lat,
            "longitude": lng,
            "daily": "temperature_2m_max,temperature_2m_min,sunrise,sunset,weather_code,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": 7,
        })
        daily = data["daily"]
        sunrise = datetime.datetime.fromisoformat(daily["sunrise"][0])
        sunset = datetime.datetime.fromisoformat(daily["sunset"][0])

        return {
            "success": True,
            "city": city.title(),
            "weather": {
                "avg_high_c": round(sum(daily["temperature_2m_max"]) / len(daily["temperature_2m_max"]), 1),
                "avg_low_c": round(sum(daily["temperature_2m_min"]) / len(daily["temperature_2m_min"]), 1),
                "condition": WMO_CONDITIONS.get(daily["weather_code"][0]),
                "rain_chance_pct": daily["precipitation_probability_max"][0],
                "sunrise": _fmt_time(sunrise),
                "sunset": _fmt_time(sunset),
                "golden_hours": {
                    "morning": f"{_fmt_time(sunrise)} - {_fmt_time(sunrise + datetime.timedelta(hours=1))}",
                    "evening": f"{_fmt_time(sunset - datetime.timedelta(hours=1))} - {_fmt_time(sunset)}",
                },
                "forecast": [
                    {
                        "date": daily["time"][i],
                        "high_c": daily["temperature_2m_max"][i],
                        "low_c": daily["temperature_2m_min"][i],
                        "condition": WMO_CONDITIONS.get(daily["weather_code"][i]),
                        "rain_chance_pct": daily["precipitation_probability_max"][i],
                    }
                    for i in range(len(daily["time"]))
                ],
            },
        }
    except Exception as e:
        logger.warning("Weather lookup failed for %s: %s", city, e)
        return {"success": False, "city": city.title(), "error": "Weather service unavailable."}
