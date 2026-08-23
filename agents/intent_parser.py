import json
import re
from typing import Optional, List
from langchain_core.tools import tool
from geopy.geocoders import Nominatim
import geocoder
from pydantic import BaseModel, Field

class EnvironmentalPreferences(BaseModel):
    prefer_green: bool = Field(default=False, description="True if user wants general green/nature areas.")
    prefer_forest: bool = Field(default=False, description="True if user wants woods, forest, or tree-covered areas.")
    prefer_park: bool = Field(default=False, description="True if user explicitly wants public parks.")
    prefer_nature_reserve: bool = Field(default=False, description="True if user requests protected nature reserves.")
    prefer_open_green: bool = Field(default=False, description="True if user requests fields, meadows, or open greenery.")
    prefer_unpaved: bool = Field(default=False, description="True if user wants dirt, unpaved, gravel, or trail paths.")
    prefer_footway_only: bool = Field(default=False, description="True if user asks for footpaths only.")
    require_lit: bool = Field(default=False, description="True if user requests illuminated paths or night walking.")
    prefer_easy: bool = Field(default=False, description="True if user needs easy, accessible, low-effort paths.")
    require_wheelchair_accessible: bool = Field(default=False, description="True if the route must be suitable for wheelchair users.")
    avoid_unpaved: bool = Field(default=False, description="True if unpaved, loose, or rough surfaces should be avoided.")
    avoid_stairs: bool = Field(default=False, description="True if stairs must be avoided.")
    avoid_steep: bool = Field(default=False, description="True if steep paths or steep inclines must be avoided.")

class RouteIntent(BaseModel):
    route_type: str = Field(default="loop", description="'loop' or 'point_to_point'")
    distance_km: float = Field(default=5.0, description="Target distance in kilometers")
    start_location_name: Optional[str] = Field(default=None, description="Explicit start location text, address, or town name (e.g., 'Grobbendonk')")
    end_location_name: Optional[str] = Field(default=None, description="Explicit end location text, address, or town name (e.g., 'Nijlen')")
    start_point: Optional[List[float]] = Field(default=None, description="[latitude, longitude] or null")
    end_point: Optional[List[float]] = Field(default=None, description="[latitude, longitude] or null")
    environmental_preferences: EnvironmentalPreferences = Field(default_factory=EnvironmentalPreferences)
    notes: str = Field(default="", description="Extra specifications about the intent")

def extract_json_block(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.S)
    return match.group(0) if match else text


def normalise_environmental_preferences(preferences: EnvironmentalPreferences, user_request: str) -> dict:
    values = preferences.model_dump()
    request = user_request.lower()

    broad_green_language = (
        "green surroundings", "natural surroundings", "natural areas", "nature areas",
        "nature everywhere", "as much nature as possible", "walk in green"
    )
    accessibility_language = (
        "wheelchair", "wheel chair", "mobility scooter", "accessible", "pram",
        "pushchair", "stroller", "reduced mobility"
    )
    easy_language = ("easy", "flat", "smooth", "low effort", "low-effort", "accessible")

    explicit_open_green = any(term in request for term in ("open green", "meadow", "field"))
    explicit_forest = any(term in request for term in ("forest", "woodland", "woods"))
    explicit_park = "park" in request
    explicit_reserve = any(term in request for term in ("nature reserve", "protected reserve"))
    broad_green = any(term in request for term in broad_green_language)

    if broad_green and not explicit_open_green:
        values.update({
            "prefer_green": True,
            "prefer_forest": True,
            "prefer_park": True,
            "prefer_nature_reserve": True,
            "prefer_open_green": True,
        })

    # Specific categories are independent. For example, open green space does
    # not imply forest, and a park request does not imply a nature reserve.
    if explicit_open_green:
        values["prefer_open_green"] = True
        values["prefer_green"] = broad_green
        if not explicit_forest:
            values["prefer_forest"] = False
        if not explicit_park:
            values["prefer_park"] = False
        if not explicit_reserve:
            values["prefer_nature_reserve"] = False
    if explicit_forest:
        values["prefer_forest"] = True
    if explicit_park:
        values["prefer_park"] = True
    if explicit_reserve:
        values["prefer_nature_reserve"] = True

    if any(term in request for term in accessibility_language):
        values.update({
            "prefer_easy": True,
            "require_wheelchair_accessible": True,
            "avoid_unpaved": True,
            "avoid_stairs": True,
            "avoid_steep": True,
            "prefer_unpaved": False,
        })

    if any(term in request for term in easy_language):
        values["prefer_easy"] = True
    if any(term in request for term in ("no stairs", "without stairs", "stair-free")):
        values["avoid_stairs"] = True
    if any(term in request for term in ("no steep", "without steep", "flat route")):
        values["avoid_steep"] = True

    if values["require_wheelchair_accessible"]:
        values["prefer_easy"] = True
        values["avoid_stairs"] = True
        values["avoid_steep"] = True
        values["avoid_unpaved"] = True
        values["prefer_unpaved"] = False

    return values

@tool
def user_location_tool() -> list:
    """
    Fetches the approximate latitude and longitude of the user based on their current IP location.
    Use this tool when the user says "my location", "current position", "here", or provides no start location.
    """
    try:
        g = geocoder.ip('me')
        if g.latlng:
            return g.latlng
    except Exception as e:
        print(f"[Location Tool] IP Geolocation failed: {e}")
    
    return None

@tool
def resolve_location_tool(location_description: str) -> Optional[list]:
    """
    Geocodes a location description, address, place name, or coordinate string into a [latitude, longitude] list.
    Use this tool whenever the user provides a specific place name, city, address, or landmark for their hike.
    
    Examples:
    - "Grobbendonk, Belgium" -> [51.1915, 4.7410]
    - "Central Park, New York" -> [40.7812, -73.9665]
    """
    if not location_description:
        return None
    
    loc_clean = location_description.strip()

    # Check for raw coordinate strings
    coord_match = re.search(r"(-?\d+\.\d+),\s*(-?\d+\.\d+)", loc_clean)
    if coord_match:
        return [float(coord_match.group(1)), float(coord_match.group(2))]

    # Address / Place Name Geocoding
    try:
        geolocator = Nominatim(user_agent="hiking_routing_agent")
        location = geolocator.geocode(loc_clean, timeout=5)
        if location:
            return [location.latitude, location.longitude]
    except Exception as e:
        print(f"[Location Tool] Geocoding error for '{loc_clean}': {e}")
    return None


def intent_parser_node(state: dict) -> dict:
    """
    Translates user natural language requests into structured routing preferences
    covering all existing database relationship properties.
    Binds tools so the LLM dynamically decides whether to geocode an address
    or query current IP location coordinates.
    """
    print("[Intent Parser] Translating user request into structured route preferences")

    llm = state.get("_llm")
    user_request = state.get("user_request", "").strip()

    if not user_request:
        user_request = (
            "Generate a 5 km loop hike in nature starting from my current position"
        )

    tools = [resolve_location_tool, user_location_tool]
    llm_structured = llm.with_structured_output(RouteIntent)

    parsed_intent = None

    prompt_intent = f"""
    You are an intelligent trail planning assistant.
    Analyze the user request and extract structured intent parameters.

    User Request: "{user_request}"

    Instructions:
    1. Identify route_type ("loop" or "point_to_point").
    2. Extract clean, concise place/city/street names for 'start_location_name' and 'end_location_name' suitable for geocoding.
       - Example: "city centre of Nijlen" -> "Nijlen"
       - Example: "my home in Grobbendonk (Tulpstraat 12)" -> "Tulpstraat 12, Grobbendonk"
        3. Reason about environmental preferences. Interpret context, not just exact words:
             - Wheelchair, mobility scooter, pram, reduced mobility, or accessible means prefer_easy=true,
                 require_wheelchair_accessible=true, avoid_unpaved=true, avoid_stairs=true, avoid_steep=true,
                 and prefer_unpaved=false.
             - Broad requests for green, nature, or natural surroundings mean prefer_green=true and also
                 prefer_forest=true, prefer_park=true, prefer_nature_reserve=true, and prefer_open_green=true.
             - Do not set prefer_unpaved for wheelchair or accessibility requests.
        4. Keep preferences consistent. Accessibility requirements override a request for unpaved paths.
    """

    try:
        # Structured extraction directly maps explicit origin/destination strings
        parsed_intent = llm_structured.invoke(prompt_intent)
    except Exception as e:
        print(f"[Intent Parser] Fallback triggered ({e}).")
        parsed_intent = RouteIntent()

    # Resolve Start Point using structured role
    final_start_point = None
    if parsed_intent.start_location_name:
        print(f"[Intent Parser] Resolving start location: '{parsed_intent.start_location_name}'")
        final_start_point = resolve_location_tool.invoke({"location_description": parsed_intent.start_location_name})

    # State / IP fallback for Start Point
    if not final_start_point:
        state_start_lat = state.get("start_lat")
        state_start_lon = state.get("start_lon")
        if state_start_lat and state_start_lon:
            final_start_point = [float(state_start_lat), float(state_start_lon)]
        elif parsed_intent.start_point:
            final_start_point = parsed_intent.start_point
        else:
            print("[Intent Parser] Fetching IP-based location fallback")
            final_start_point = user_location_tool.invoke({})

    # Resolve End Point using structured role
    final_end_point = None
    if parsed_intent.end_location_name:
        print(f"[Intent Parser] Resolving end location: '{parsed_intent.end_location_name}'")
        final_end_point = resolve_location_tool.invoke({"location_description": parsed_intent.end_location_name})
    elif parsed_intent.end_point:
        final_end_point = parsed_intent.end_point

    route_type = parsed_intent.route_type.lower()
    if route_type not in ["loop", "point_to_point"]:
        route_type = "loop"

    # Ensure point-to-point requests resolve missing destination explicitly
    if route_type == "point_to_point" and not final_end_point:
        dest_prompt = f"Extract ONLY the destination location/address/city from this request: '{user_request}'"
        dest_response = llm.invoke(dest_prompt)
        dest_str = getattr(dest_response, "content", "").strip()
        
        if dest_str:
            print(f"[Intent Parser] Secondary resolution for destination: '{dest_str}'")
            final_end_point = resolve_location_tool.invoke({"location_description": dest_str})

    # Safeguard for loops
    if route_type == "loop" and not final_end_point:
        final_end_point = final_start_point

    final_route_request = {
        "route_type": route_type,
        "distance_km": float(parsed_intent.distance_km),
        "start_point": final_start_point,
        "end_point": final_end_point,
        "environmental_preferences": normalise_environmental_preferences(
            parsed_intent.environmental_preferences, user_request
        ),
        "notes": parsed_intent.notes or user_request
    }

    print(
        f"[Intent Parser] Successfully Parsed -> "
        f"route_type={final_route_request['route_type']}, "
        f"distance_km={final_route_request['distance_km']}, "
        f"start_point={final_route_request['start_point']}, "
        f"end_point={final_route_request['end_point']}, "
        f"env_prefs={final_route_request['environmental_preferences']}"
    )

    return {"route_request": final_route_request}