import json
import re
from datetime import date
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
    prefer_paved: bool = Field(default=False, description="True if user wants paved or firm surfaces.")
    prefer_footway_only: bool = Field(default=False, description="True if user asks for footpaths only.")
    require_lit: bool = Field(default=False, description="True if user requests illuminated paths or night walking.")
    prefer_easy: bool = Field(default=False, description="True if user needs easy, accessible, low-effort paths.")
    require_wheelchair_accessible: bool = Field(default=False, description="True if the route must be suitable for wheelchair users.")
    avoid_unpaved: bool = Field(default=False, description="True if unpaved, loose, or rough surfaces should be avoided.")
    avoid_green: bool = Field(default=False, description="True if green or nature areas should be avoided.")
    avoid_forest: bool = Field(default=False, description="True if forested paths should be avoided.")
    avoid_park: bool = Field(default=False, description="True if public parks should be avoided.")
    avoid_nature_reserve: bool = Field(default=False, description="True if nature reserves should be avoided.")
    avoid_open_green: bool = Field(default=False, description="True if fields and open green spaces should be avoided.")
    avoid_footways: bool = Field(default=False, description="True if footways and paths should be avoided.")
    avoid_lit: bool = Field(default=False, description="True if illuminated paths should be avoided.")
    avoid_stairs: bool = Field(default=False, description="True if stairs must be avoided.")
    avoid_steep: bool = Field(default=False, description="True if steep paths or steep inclines must be avoided.")
    avoid_mud: bool = Field(default=False, description="True if the user wants to avoid muddy paths or mud.")

class RouteIntent(BaseModel):
    route_type: str = Field(default="loop", description="'loop' or 'point_to_point'")
    distance_km: Optional[float] = Field(default=None, description="Target distance in kilometers, or null when the user does not specify one")
    start_location_name: Optional[str] = Field(default=None, description="Explicit start location text, address, or town name (e.g., 'Grobbendonk')")
    end_location_name: Optional[str] = Field(default=None, description="Explicit end location text, address, or town name (e.g., 'Nijlen')")
    start_point: Optional[List[float]] = Field(default=None, description="[latitude, longitude] or null")
    end_point: Optional[List[float]] = Field(default=None, description="[latitude, longitude] or null")
    via_location_name: Optional[str] = Field(default=None, description="A place or address the route must pass through, if explicitly requested")
    via_point: Optional[List[float]] = Field(default=None, description="[latitude, longitude] for a mandatory pass-through point, or null")
    hike_date: Optional[str] = Field(default=None, description="Hiking date as YYYY-MM-DD; use today when explicitly requested and null when no day is specified")
    environmental_preferences: EnvironmentalPreferences = Field(default_factory=EnvironmentalPreferences)
    notes: str = Field(default="", description="Extra specifications about the intent")

def extract_json_block(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.S)
    return match.group(0) if match else text


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
         Extract distance_km as a positive number only when the user explicitly specifies a distance.
         Return distance_km=null when no distance is stated; never use 0 or invent a default distance.
            Extract hike_date as YYYY-MM-DD when the request says today, tomorrow, a weekday, or gives a date.
             Resolve relative dates using today's date: {date.today().isoformat()}.
            Return hike_date=null when no hiking day is mentioned.
     2. Extract clean, concise place/city/street names for 'start_location_name', 'end_location_name', and
         'via_location_name' suitable for geocoding.
       - Example: "city centre of Nijlen" -> "Nijlen"
       - Example: "my home in Grobbendonk (Tulpstraat 12)" -> "Tulpstraat 12, Grobbendonk"
         - Set via_location_name only when the user explicitly says the route must pass through, visit,
            or include a location. It can be a city, landmark, address, or coordinate pair.
                3. Reason carefully about every environmental preference. Set a field to true only when the request
                     expresses that preference, requirement, or avoidance; otherwise leave it false.
                     - Green: prefer_green is for a general request for nature or green surroundings. Use prefer_forest,
                         prefer_park, prefer_nature_reserve, or prefer_open_green only when that specific setting is requested.
                         Set avoid_green, avoid_forest, avoid_park, avoid_nature_reserve, or avoid_open_green when the user
                         explicitly wants to stay away from the corresponding setting.
                     - Surfaces: prefer_unpaved is for dirt, gravel, trails, or natural surfaces. prefer_paved is for paved,
                         firm, smooth, or tarmac paths. avoid_unpaved is for an explicit request to avoid loose, rough,
                         gravel, dirt, or unpaved surfaces.
                     - Mud: set avoid_mud when the user mentions mud, muddy paths, dirty shoes, or keeping shoes clean.
                         Do not infer avoid_unpaved or prefer_paved from avoid_mud; the weather agent decides that later.
                     - Path type: set prefer_footway_only when the user wants footpaths only. Set avoid_footways when they
                         explicitly want to avoid footways, paths, tracks, or pedestrian paths.
                     - Lighting: require_lit is for illuminated routes or walking at night. avoid_lit is only for an explicit
                         request to avoid illuminated paths.
                     - Accessibility: wheelchair, mobility scooter, pram, reduced mobility, or an explicit accessibility
                         requirement means require_wheelchair_accessible=true, prefer_easy=true, avoid_unpaved=true,
                         avoid_stairs=true, avoid_steep=true, prefer_unpaved=false, and prefer_paved=true.
                         Set prefer_easy for an easy, smooth, low-effort, or flat route. Set avoid_stairs and avoid_steep only
                         when stairs or steep terrain must be avoided.
                  4. Resolve conflicts deliberately. Explicit avoidance overrides a matching preference. In particular,
                      avoid_green=true means prefer_green, prefer_forest, prefer_park, prefer_nature_reserve, and
                      prefer_open_green must all be false. Likewise, avoiding a specific green category means its matching
                      preference must be false. Accessibility requirements override any request for unpaved, stairs, or
                      steep terrain. Do not invent preferences.
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

    # Resolve an explicitly requested mandatory pass-through point.
    final_via_point = None
    if parsed_intent.via_location_name:
        print(f"[Intent Parser] Resolving pass-through location: '{parsed_intent.via_location_name}'")
        final_via_point = resolve_location_tool.invoke(
            {"location_description": parsed_intent.via_location_name}
        )
    elif parsed_intent.via_point:
        final_via_point = parsed_intent.via_point

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

    requested_distance = parsed_intent.distance_km
    if requested_distance is not None and requested_distance <= 0:
        requested_distance = None

    final_route_request = {
        "route_type": route_type,
        "distance_km": requested_distance,
        "start_point": final_start_point,
        "end_point": final_end_point,
        "via_point": final_via_point,
        "via_location_name": parsed_intent.via_location_name,
        "hike_date": parsed_intent.hike_date,
        "environmental_preferences": parsed_intent.environmental_preferences.model_dump(),
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