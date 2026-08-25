# -----------------------------------------------
# GPX FILE GENERATOR FROM ROUTE COORDINATES
# -----------------------------------------------

import json
from datetime import datetime
from typing import List, Optional


def generate_gpx(
    coordinates: List[tuple],
    route_name: str = "AI Trail Planner Route",
    route_description: str = "",
    distance_km: Optional[float] = None,
) -> str:
    """
    Generate a GPX 1.1 file from a list of (lat, lon) coordinates.
    Coordinates should be ordered along the route.
    """
    if not coordinates or len(coordinates) < 2:
        raise ValueError("At least 2 coordinates are required to generate a GPX file.")

    timestamp = datetime.utcnow().isoformat() + "Z"
    gpx_header = f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="AI Trail Planner" xmlns="http://www.topografix.com/GPX/1/1"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
  <metadata>
    <name>{route_name}</name>
    <desc>{route_description}</desc>
    <time>{timestamp}</time>
  </metadata>
  <trk>
    <name>{route_name}</name>
    <desc>{route_description}</desc>
    <trkseg>
"""

    trackpoints = []
    for lat, lon in coordinates:
        trackpoints.append(f'      <trkpt lat="{lat}" lon="{lon}">\n        <time>{timestamp}</time>\n      </trkpt>')

    gpx_footer = """    </trkseg>
  </trk>
</gpx>"""

    return gpx_header + "\n".join(trackpoints) + "\n" + gpx_footer


def extract_coordinates_for_gpx(neo4j_data: List[dict]) -> List[tuple]:
    """Extract coordinates from the route data structure (same as map generator)."""
    import json

    if not neo4j_data or not isinstance(neo4j_data, list):
        return []

    if isinstance(neo4j_data[0], dict):
        nodes = neo4j_data[0].get("path_nodes") or []
        edges = neo4j_data[0].get("edge_details") or []
        coordinates = []

        for index, node in enumerate(nodes):
            if isinstance(node, dict):
                lat = node.get("lat") or node.get("latitude")
                lon = node.get("lon") or node.get("longitude")
                if lat is not None and lon is not None:
                    coord = (float(lat), float(lon))
                    if not coordinates or coordinates[-1] != coord:
                        coordinates.append(coord)

            if index >= len(edges):
                continue
            geometry = edges[index].get("geometry") if isinstance(edges[index], dict) else None
            if not geometry:
                continue
            try:
                geometry_points = json.loads(geometry) if isinstance(geometry, str) else geometry
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            for point in geometry_points:
                if isinstance(point, (list, tuple)) and len(point) == 2:
                    coordinate = (float(point[0]), float(point[1]))
                    if not coordinates or coordinates[-1] != coordinate:
                        coordinates.append(coordinate)

        return coordinates

    return []
