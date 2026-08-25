import logging
import random
from typing import Any, List, Optional


logger = logging.getLogger(__name__)

UNPAVED_SURFACES = ["unpaved", "dirt", "gravel", "ground", "compacted"]
WALKING_HIGHWAYS = ["footway", "path", "pedestrian", "track", "bridleway"]
FOREST_HIGHWAYS = ["path", "track", "bridleway"]


def execute_cypher_query(graph_service: Any, query: str, params: dict) -> List[dict]:
    if hasattr(graph_service, "graph") and hasattr(graph_service.graph, "query"):
        return graph_service.graph.query(query, params)
    if hasattr(graph_service, "query"):
        return graph_service.query(query, params)
    if hasattr(graph_service, "run"):
        return graph_service.run(query, params)
    raise AttributeError("Could not find a valid execution query method on 'graph_service'.")


def build_preference_cost_expression(
    env_prefs: dict, weather_report: Optional[dict] = None
) -> str:
    cost = "coalesce(r.distance, 1.0)"
    forest = (
        "(coalesce(r.is_forest, 'no') = 'yes' "
        "OR coalesce(r.landuse, '') IN ['forest', 'orchard'] "
        "OR coalesce(r.natural, '') IN ['wood', 'scrub', 'heath'] "
        f"OR r.highway IN {FOREST_HIGHWAYS})"
    )
    green = (
        "(coalesce(r.is_green, 'no') = 'yes' OR "
        f"{forest} OR coalesce(r.is_park, 'no') = 'yes' OR "
        "coalesce(r.is_nature_reserve, 'no') = 'yes' OR "
        "coalesce(r.is_open_green, 'no') = 'yes')"
    )
    unpaved = (
        "(coalesce(r.is_unpaved, 'no') = 'yes' "
        f"OR r.surface IN {UNPAVED_SURFACES})"
    )

    if env_prefs.get("prefer_green"):
        cost = f"CASE WHEN {green} THEN ({cost} * 0.45) ELSE ({cost} * 1.8) END"

    preferred = []
    if env_prefs.get("prefer_forest"):
        preferred.append(forest)
    if env_prefs.get("prefer_park"):
        preferred.append("coalesce(r.is_park, 'no') = 'yes'")
    if env_prefs.get("prefer_nature_reserve"):
        preferred.append("coalesce(r.is_nature_reserve, 'no') = 'yes'")
    if env_prefs.get("prefer_open_green"):
        preferred.append("coalesce(r.is_open_green, 'no') = 'yes'")
    if preferred:
        cost = f"CASE WHEN ({' OR '.join(preferred)}) THEN ({cost} * 0.25) ELSE ({cost} * 3.0) END"

    if env_prefs.get("prefer_unpaved"):
        cost = f"CASE WHEN {unpaved} THEN ({cost} * 0.6) ELSE ({cost} * 1.4) END"
    if env_prefs.get("avoid_unpaved"):
        cost = f"CASE WHEN {unpaved} THEN ({cost} * 12.0) ELSE ({cost}) END"
    if env_prefs.get("prefer_footway_only"):
        cost = f"CASE WHEN r.highway IN {WALKING_HIGHWAYS} THEN ({cost} * 0.7) ELSE ({cost} * 2.5) END"
    if env_prefs.get("require_lit"):
        cost = f"CASE WHEN coalesce(r.lit, 'no') IN ['yes', 'true'] THEN ({cost} * 0.8) ELSE ({cost} * 2.0) END"
    if env_prefs.get("prefer_easy"):
        cost = (
            f"CASE WHEN coalesce(r.smoothness, 'unknown') IN ['excellent', 'good', 'intermediate'] "
            f"OR r.surface IN ['paved', 'asphalt', 'concrete', 'paving_stones'] "
            f"THEN ({cost} * 0.65) ELSE ({cost} * 2.2) END"
        )
    if env_prefs.get("require_wheelchair_accessible"):
        cost = f"CASE WHEN coalesce(r.wheelchair, 'no') IN ['yes', 'designated'] THEN ({cost} * 0.5) ELSE ({cost} * 8.0) END"
    if env_prefs.get("avoid_stairs"):
        cost = f"CASE WHEN r.highway = 'steps' THEN ({cost} * 20.0) ELSE ({cost}) END"
    if env_prefs.get("avoid_steep"):
        cost = f"CASE WHEN coalesce(r.incline, '') IN ['up', 'down', '10%', '15%', '20%', '25%'] THEN ({cost} * 5.0) ELSE ({cost}) END"

    return cost


def _resolve_nodes(graph_service: Any, route_request: dict, state: dict) -> Optional[dict]:
    start_point = route_request.get("start_point")
    if not start_point:
        return None
    start_id = state.get("start_node_id") or graph_service.get_closest_node_id(*start_point)
    end_id = state.get("end_node_id")
    end_point = route_request.get("end_point")
    if route_request.get("route_type") == "point_to_point" and end_point:
        end_id = end_id or graph_service.get_closest_node_id(*end_point)
    else:
        end_id = end_id or start_id

    via_id = None
    if route_request.get("via_point"):
        via_id = graph_service.get_closest_node_id(*route_request["via_point"])
    if not start_id or not end_id or route_request.get("via_point") and not via_id:
        return None
    return {"start_id": start_id, "end_id": end_id, "via_id": via_id}


def _waypoint_query(route_type: str) -> str:
    if route_type == "loop":
        return """
        MATCH (s:OSMNode), (w:OSMNode)
        WHERE elementId(s) = $start_id AND w.location IS NOT NULL
        WITH s, w, point.distance(s.location, w.location) AS radial_dist
        WHERE elementId(w) <> $start_id
          AND radial_dist >= ($search_radius_m * 0.08)
          AND radial_dist <= ($search_radius_m * 0.62)
        WITH elementId(w) AS waypoint_id
        ORDER BY rand()
        LIMIT 48
        RETURN waypoint_id
        """
    return """
    MATCH (s:OSMNode), (e:OSMNode)
    WHERE elementId(s) = $start_id AND elementId(e) = $end_id
    WITH s, e, point.distance(s.location, e.location) AS direct_dist
    MATCH (w:OSMNode)
    WHERE w.location IS NOT NULL
    WITH s, e, direct_dist, w,
         point.distance(w.location, s.location) AS d_start,
         point.distance(w.location, e.location) AS d_end
    WHERE d_start > direct_dist * 0.2 AND d_end > direct_dist * 0.2
      AND d_start < direct_dist * 1.1 AND d_end < direct_dist * 1.1
    WITH elementId(w) AS waypoint_id
    ORDER BY rand()
    LIMIT 36
    RETURN waypoint_id
    """


def _leg_query(return_leg: bool, route_type: str, weighted: bool = True) -> str:
    overlap_filter = ""
    road_filter = ""
    if return_leg and route_type == "loop":
        road_filter = """
        WHERE ALL(rel IN relationships(path)
            WHERE NOT (elementId(startNode(rel)) + '|' + elementId(endNode(rel)) IN $forbidden_pairs
                OR elementId(endNode(rel)) + '|' + elementId(startNode(rel)) IN $forbidden_pairs))
        """
    elif return_leg:
        overlap_filter = """
        WITH path, [n IN nodes(path) | elementId(n)] AS node_ids
        WHERE $allow_overlap OR NONE(id IN node_ids[..-1] WHERE id IN $forbidden_nodes)
        """
    path_match = (
        "CALL apoc.algo.dijkstra(a, b, 'CONNECTED_TO', 'temp_cost') YIELD path"
        if weighted else
        "MATCH path = shortestPath((a)-[:CONNECTED_TO*..100]->(b))"
    )
    return f"""
    MATCH (a:OSMNode), (b:OSMNode)
    WHERE elementId(a) = $from_id AND elementId(b) = $to_id
    {path_match}
    {overlap_filter}
    {road_filter}
    RETURN path,
           [n IN nodes(path) | elementId(n)] AS node_ids,
           [r IN relationships(path) | {{forward: elementId(startNode(r)) + '|' + elementId(endNode(r)), reverse: elementId(endNode(r)) + '|' + elementId(startNode(r))}}] AS road_pairs,
           [n IN nodes(path) | {{lat: n.lat, lon: n.lon, id: coalesce(n.id, elementId(n))}}] AS nodes_data,
           [r IN relationships(path) | {{highway: r.highway, surface: r.surface, distance: r.distance, smoothness: r.smoothness, wheelchair: r.wheelchair, incline: r.incline, lit: r.lit}}] AS rels_data,
           reduce(d = 0.0, r IN relationships(path) | d + coalesce(r.distance, 1.0)) AS distance,
           reduce(c = 0.0, r IN relationships(path) | c + coalesce(r.temp_cost, 1.0)) AS cost
    """


def _format_route(first: dict, second: dict, via_id: Optional[str]) -> list:
    return [{
        "path_nodes": first["nodes_data"] + second["nodes_data"][1:],
        "edge_details": first["rels_data"] + second["rels_data"],
        "totalDistance": first["distance"] + second["distance"],
        "totalCost": first["cost"] + second["cost"],
        "via_node_id": via_id,
    }]


def routing_node(state: dict) -> dict:
    route_request = state.get("route_request") or {}
    route_type = route_request.get("route_type", "loop")
    target_km = route_request.get("distance_km")
    graph_service = state["_graph_service"]
    nodes = _resolve_nodes(graph_service, route_request, state)
    if not nodes:
        return {"raw_route_data": None, "is_valid": False, "error_message": "Missing route position or network node."}

    cost_expression = build_preference_cost_expression(
        route_request.get("environmental_preferences") or {}, state.get("weather_report")
    )
    execute_cypher_query(
        graph_service,
        f"MATCH ()-[r:CONNECTED_TO]->() SET r.temp_cost = {cost_expression}",
        {},
    )

    search_radius_m = float(target_km or 8.0) * 1000.0
    waypoints = execute_cypher_query(
        graph_service,
        _waypoint_query(route_type),
        {"start_id": str(nodes["start_id"]), "end_id": str(nodes["end_id"]), "search_radius_m": search_radius_m},
    )
    print(f"[Routing Agent Node] Waypoint candidates found: {len(waypoints or [])}")
    candidates = []
    first_query = _leg_query(False, route_type)
    second_query = _leg_query(True, route_type)
    distance_tolerance = max(2.0, target_km * 0.25) if target_km is not None else None

    for waypoint in waypoints or []:
        waypoint_id = str(waypoint["waypoint_id"])
        first_result = execute_cypher_query(
            graph_service, first_query, {"from_id": str(nodes["start_id"]), "to_id": waypoint_id}
        )
        if not first_result:
            continue
        first = first_result[0]
        if nodes["via_id"] and str(nodes["via_id"]) not in {str(node_id) for node_id in first["node_ids"]}:
            continue
        if target_km is not None and first["distance"] > (target_km + distance_tolerance) * 1000:
            continue

        forbidden_pairs = []
        for pair in first.get("road_pairs", []):
            forbidden_pairs.extend((pair["forward"], pair["reverse"]))
        second_params = {
            "from_id": waypoint_id,
            "to_id": str(nodes["end_id"]),
            "forbidden_nodes": first["node_ids"][:-1],
            "forbidden_pairs": forbidden_pairs,
            "allow_overlap": False,
        }
        second_result = execute_cypher_query(graph_service, second_query, second_params)
        if not second_result and route_type == "loop":
            second_result = execute_cypher_query(
                graph_service,
                _leg_query(True, route_type, weighted=False),
                second_params,
            )
        if not second_result and route_type == "point_to_point" and nodes["via_id"]:
            second_params["allow_overlap"] = True
            second_result = execute_cypher_query(graph_service, second_query, second_params)
        if not second_result:
            continue

        second = second_result[0]
        distance_m = first["distance"] + second["distance"]
        distance_km = distance_m / 1000.0
        distance_difference = abs(distance_km - target_km) if target_km is not None else 0.0
        preference_cost = (first["cost"] + second["cost"]) / max(distance_m, 1.0)
        candidates.append({
            "distance_difference": distance_difference,
            "preference_cost": preference_cost,
            "distance_km": distance_km,
            "route": _format_route(first, second, nodes["via_id"]),
        })

    if not candidates:
        print("[Routing Agent Node] No valid route candidates survived path checks.")
        return {"raw_route_data": None, "is_valid": False, "error_message": "No valid route found."}

    if target_km is not None:
        candidates = [candidate for candidate in candidates if candidate["distance_difference"] <= distance_tolerance]
        if not candidates:
            return {"raw_route_data": None, "is_valid": False, "error_message": "No route found within the requested distance tolerance."}

    candidates.sort(key=lambda candidate: (candidate["preference_cost"], candidate["distance_difference"]))
    selected = random.SystemRandom().choice(candidates[: min(5, len(candidates))])
    print(f"[Routing Agent Node] Selected {route_type} route: {selected['distance_km']:.2f} km")
    return {
        "start_node_id": nodes["start_id"],
        "end_node_id": nodes["end_id"],
        "via_node_id": nodes["via_id"],
        "raw_route_data": selected["route"],
        "is_valid": True,
        "error_message": None,
    }