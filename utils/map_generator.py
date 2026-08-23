# ---------------------------------------
# MAP GENERATOR FUNCTIONS
# ---------------------------------------

import folium
from shapely.geometry import LineString


def _extract_coordinates_from_node(node):
    if node is None:
        return None

    if isinstance(node, dict):
        if "location" in node and isinstance(node["location"], dict):
            loc = node["location"]
            latitude = loc.get("latitude") or loc.get("lat")
            longitude = loc.get("longitude") or loc.get("lon")
            if latitude is not None and longitude is not None:
                return (latitude, longitude)

        if "lat" in node and "lon" in node:
            return (node["lat"], node["lon"])
        if "latitude" in node and "longitude" in node:
            return (node["latitude"], node["longitude"])

        for value in node.values():
            if isinstance(value, dict):
                coord = _extract_coordinates_from_node(value)
                if coord:
                    return coord

    if hasattr(node, "get"):
        lat = node.get("lat") or node.get("latitude")
        lon = node.get("lon") or node.get("longitude")
        if lat is not None and lon is not None:
            return (lat, lon)

    return None


def _extract_path_nodes(path_object):
    if path_object is None:
        return []

    if hasattr(path_object, "nodes"):
        return list(path_object.nodes)

    if isinstance(path_object, dict):
        if "nodes" in path_object and isinstance(path_object["nodes"], list):
            return path_object["nodes"]
        if "segments" in path_object and isinstance(path_object["segments"], list):
            nodes = []
            for segment in path_object["segments"]:
                if isinstance(segment, dict):
                    if "start" in segment:
                        nodes.append(segment["start"])
                    if "end" in segment:
                        nodes.append(segment["end"])
            return nodes

    if isinstance(path_object, (list, tuple)):
        return list(path_object)

    return []


def _collect_coordinates_from_record(record):
    coordinates = []
    if isinstance(record, dict):
        for value in record.values():
            if value is None:
                continue

            path_nodes = _extract_path_nodes(value)
            if path_nodes:
                for node in path_nodes:
                    coord = _extract_coordinates_from_node(node)
                    if coord and coord[0] is not None and coord[1] is not None:
                        if not coordinates or coordinates[-1] != coord:
                            coordinates.append(coord)
            else:
                coord = _extract_coordinates_from_node(value)
                if coord and coord[0] is not None and coord[1] is not None:
                    if not coordinates or coordinates[-1] != coord:
                        coordinates.append(coord)
    return coordinates


def create_map_from_neo4j_output(neo4j_data, output_html="output/route_map.html", route_type="loop"):
    """
    Parses Neo4j query output into ordered coordinates and generates a Folium map.
    Supports both loop routes and point-to-point routes.
    """
    if not neo4j_data or not isinstance(neo4j_data, list):
        print("Error: Invalid or empty Neo4j data structure.")
        return False

    coordinates = []
    for record in neo4j_data:
        coordinates = _collect_coordinates_from_record(record)
        if coordinates:
            break

    if len(coordinates) < 2:
        print("Error: Not enough coordinates found to build the route.")
        return False

    if route_type == "loop" and coordinates[0] != coordinates[-1]:
        coordinates.append(coordinates[0])

    shapely_coords = [(lon, lat) for lat, lon in coordinates]
    LineString(shapely_coords)

    print(f"Success: Shapely LineString created with {len(coordinates)} points.")
    if isinstance(neo4j_data[0], dict) and "totalDistance" in neo4j_data[0]:
        print(f"Total calculated distance: {round(neo4j_data[0]['totalDistance'], 2)} meters.")

    start_lat, start_lon = coordinates[0]
    m = folium.Map(location=[start_lat, start_lon], zoom_start=14, control_scale=True)

    folium.PolyLine(
        locations=coordinates,
        color="blue",
        weight=5,
        opacity=0.75,
        tooltip="AI Trail Planner - Generated Route"
    ).add_to(m)

    folium.Marker(
        location=[start_lat, start_lon],
        popup="Start",
        icon=folium.Icon(color="green", icon="play")
    ).add_to(m)

    if route_type != "loop" and coordinates[-1] != coordinates[0]:
        end_lat, end_lon = coordinates[-1]
        folium.Marker(
            location=[end_lat, end_lon],
            popup="End",
            icon=folium.Icon(color="red", icon="flag")
        ).add_to(m)
    else:
        folium.Marker(
            location=[start_lat, start_lon],
            popup="Start & Finish",
            icon=folium.Icon(color="green", icon="play")
        ).add_to(m)

    m.save(output_html)
    print(f"Success: Interactive route map saved to '{output_html}'.")
    return True