import logging
import random
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

def execute_cypher_query(graph_service: Any, query: str, params: dict) -> List[dict]:
    if hasattr(graph_service, "graph") and hasattr(graph_service.graph, "query"):
        return graph_service.graph.query(query, params)
    elif hasattr(graph_service, "query"):
        return graph_service.query(query, params)
    elif hasattr(graph_service, "run"):
        return graph_service.run(query, params)
    else:
        raise AttributeError("Could not find a valid execution query method on 'graph_service'.")


def build_preference_cost_expression(env_prefs: dict) -> str:
    base_dist = "coalesce(r.distance, 1.0)"
    cost_expr = base_dist

    if env_prefs.get("prefer_green"):
        cost_expr = (
            f"CASE WHEN coalesce(r.is_green, 'no') = 'yes' "
            f"THEN ({cost_expr} * 0.55) ELSE ({cost_expr} * 1.5) END"
        )

    if any(env_prefs.get(key) for key in (
        "prefer_forest", "prefer_park", "prefer_nature_reserve", "prefer_open_green"
    )):
        green_properties = []
        if env_prefs.get("prefer_forest"):
            green_properties.append("r.is_forest")
        if env_prefs.get("prefer_park"):
            green_properties.append("r.is_park")
        if env_prefs.get("prefer_nature_reserve"):
            green_properties.append("r.is_nature_reserve")
        if env_prefs.get("prefer_open_green"):
            green_properties.append("r.is_open_green")
        green_match = " OR ".join(f"coalesce({property_name}, 'no') = 'yes'" for property_name in green_properties)
        cost_expr = (
            f"CASE WHEN {green_match} "
            f"THEN ({cost_expr} * 0.5) ELSE ({cost_expr} * 1.8) END"
        )

    if env_prefs.get("prefer_unpaved"):
        cost_expr = (
            f"CASE WHEN coalesce(r.is_unpaved, 'no') = 'yes' "
            f"OR r.surface IN ['unpaved', 'dirt', 'gravel', 'ground', 'compacted'] "
            f"THEN ({cost_expr} * 0.6) ELSE ({cost_expr} * 1.4) END"
        )

    if env_prefs.get("avoid_unpaved"):
        cost_expr = (
            f"CASE WHEN coalesce(r.is_unpaved, 'no') = 'yes' "
            f"THEN ({cost_expr} * 12.0) ELSE ({cost_expr}) END"
        )

    if env_prefs.get("prefer_footway_only"):
        cost_expr = (
            f"CASE WHEN r.highway IN ['footway', 'path', 'pedestrian'] "
            f"THEN ({cost_expr} * 0.7) ELSE ({cost_expr} * 2.5) END"
        )

    if env_prefs.get("require_lit"):
        cost_expr = (
            f"CASE WHEN coalesce(r.lit, 'no') IN ['yes', 'true'] "
            f"THEN ({cost_expr} * 0.8) ELSE ({cost_expr} * 2.0) END"
        )

    if env_prefs.get("prefer_easy"):
        cost_expr = (
            f"CASE WHEN coalesce(r.smoothness, 'unknown') IN ['excellent', 'good', 'intermediate'] "
            f"OR r.surface IN ['paved', 'asphalt', 'concrete', 'paving_stones'] "
            f"THEN ({cost_expr} * 0.65) ELSE ({cost_expr} * 2.2) END"
        )

    if env_prefs.get("require_wheelchair_accessible"):
        cost_expr = (
            f"CASE WHEN coalesce(r.wheelchair, 'no') IN ['yes', 'designated'] "
            f"THEN ({cost_expr} * 0.5) ELSE ({cost_expr} * 8.0) END"
        )

    if env_prefs.get("avoid_stairs"):
        cost_expr = (
            f"CASE WHEN r.highway = 'steps' "
            f"THEN ({cost_expr} * 20.0) ELSE ({cost_expr}) END"
        )

    if env_prefs.get("avoid_steep"):
        cost_expr = (
            f"CASE WHEN coalesce(r.incline, '') IN ['up', 'down', '10%', '15%', '20%', '25%'] "
            f"THEN ({cost_expr} * 5.0) ELSE ({cost_expr}) END"
        )

    return cost_expr


def routing_node(state: dict) -> dict:
    retry_count = state.get("retry_count", 0)
    print(f"--- [Routing Agent Node] Execution started (Attempt: {retry_count + 1}) ---")
    
    graph_service = state["_graph_service"]
    route_request = state.get("route_request") or {}
    
    start_point = route_request.get("start_point")
    end_point = route_request.get("end_point")
    target_km = route_request.get("distance_km", 15.0)
    
    if not start_point:
        return {"raw_route_data": None, "is_valid": False, "error_message": "Missing start point."}

    start_node_id = state.get("start_node_id")
    end_node_id = state.get("end_node_id")

    if not start_node_id:
        start_node_id = graph_service.get_closest_node_id(start_point[0], start_point[1])
        print(f"[Routing Agent Node] Resolved Start Node: {start_node_id}")

    if not end_node_id:
        if route_request.get("route_type") == "point_to_point" and end_point:
            end_node_id = graph_service.get_closest_node_id(end_point[0], end_point[1])
        else:
            end_node_id = start_node_id
        print(f"[Routing Agent Node] Resolved End Node:   {end_node_id}")

    env_prefs = route_request.get("environmental_preferences", {})
    cost_expression = build_preference_cost_expression(env_prefs)

    # 1. Update edge weights with mild random variance
    update_costs_cypher = f"""
    MATCH ()-[r:CONNECTED_TO]->()
    SET r.temp_cost = ({cost_expression}) * (0.85 + (rand() * 0.3))
    """

    # Loops have identical start and end nodes, so midpoint constraints would
    # produce a zero-distance search and no possible waypoints.
    if route_request.get("route_type") == "loop":
        find_waypoints_cypher = """
        MATCH (startNode:OSMNode)
        WHERE elementId(startNode) = $start_node_id
        MATCH (w:OSMNode)
        WHERE w.location IS NOT NULL
        WITH startNode, w, point.distance(w.location, startNode.location) AS radial_dist
        WHERE elementId(w) <> $start_node_id
          AND radial_dist >= ($target_m * 0.05)
                    AND radial_dist <= ($target_m * 0.60)
        RETURN elementId(w) AS waypoint_id
        LIMIT 120
        """
    else:
        # Point-to-point routes use a midpoint-bounded waypoint search to
        # avoid routes that overshoot the destination.
        find_waypoints_cypher = """
                MATCH (startNode:OSMNode), (endNode:OSMNode)
                WHERE elementId(startNode) = $start_node_id AND elementId(endNode) = $end_node_id
                WITH startNode, endNode, point.distance(startNode.location, endNode.location) AS direct_dist
                MATCH (w:OSMNode)
                WITH startNode, endNode, direct_dist, w,
                         point.distance(w.location, startNode.location) AS d_start,
                         point.distance(w.location, endNode.location) AS d_end
                WHERE d_start > (direct_dist * 0.3)
                    AND d_end > (direct_dist * 0.3)
                    AND d_start < (direct_dist * 0.95)
                    AND d_end < (direct_dist * 0.95)
                    AND (d_start + d_end) <= (direct_dist * 1.35)
                RETURN elementId(w) AS waypoint_id
                LIMIT 60
                """

    # Leg 1 Cypher
    leg1_cypher = """
    MATCH (s:OSMNode), (w:OSMNode)
    WHERE elementId(s) = $start_id AND elementId(w) = $waypoint_id
    CALL apoc.algo.dijkstra(s, w, 'CONNECTED_TO', 'temp_cost') YIELD path
    RETURN path,
           [n IN nodes(path) | elementId(n)] AS node_ids,
           [r IN relationships(path) | elementId(r)] AS relationship_ids,
                     [r IN relationships(path) | {
                         forward: elementId(startNode(r)) + '|' + elementId(endNode(r)),
                         reverse: elementId(endNode(r)) + '|' + elementId(startNode(r))
                     }] AS road_pairs,
           [n IN nodes(path) | {lat: n.lat, lon: n.lon, id: coalesce(n.id, elementId(n))}] AS nodes_data,
                     [r IN relationships(path) | {highway: r.highway, surface: r.surface, distance: r.distance,
                         smoothness: r.smoothness, wheelchair: r.wheelchair, incline: r.incline, lit: r.lit}] AS rels_data,
           reduce(d = 0.0, r IN relationships(path) | d + coalesce(r.distance, 1.0)) AS distance,
           reduce(c = 0.0, r IN relationships(path) | c + coalesce(r.temp_cost, 1.0)) AS cost
    """

    # Point-to-point leg 2 remains disjoint. Loops use a separate return query
    # because the return path is expected to reuse network nodes.
    leg2_disjoint_cypher = """
    MATCH (w:OSMNode), (e:OSMNode)
    WHERE elementId(w) = $waypoint_id AND elementId(e) = $end_id
    CALL apoc.algo.dijkstra(w, e, 'CONNECTED_TO', 'temp_cost') YIELD path
    WITH path, [n IN nodes(path) | elementId(n)] AS n_ids
    WHERE $allow_overlap OR NONE(id IN n_ids[..-1] WHERE id IN $forbidden_nodes)
    RETURN path,
           n_ids AS node_ids,
           [n IN nodes(path) | {lat: n.lat, lon: n.lon, id: coalesce(n.id, elementId(n))}] AS nodes_data,
                     [r IN relationships(path) | {highway: r.highway, surface: r.surface, distance: r.distance,
                         smoothness: r.smoothness, wheelchair: r.wheelchair, incline: r.incline, lit: r.lit}] AS rels_data,
           reduce(d = 0.0, r IN relationships(path) | d + coalesce(r.distance, 1.0)) AS distance,
           reduce(c = 0.0, r IN relationships(path) | c + coalesce(r.temp_cost, 1.0)) AS cost
    """

    leg2_loop_no_backtrack_cypher = """
        MATCH (w:OSMNode), (e:OSMNode)
        WHERE elementId(w) = $waypoint_id AND elementId(e) = $end_id
        MATCH path = shortestPath((w)-[:CONNECTED_TO*..100]->(e))
        WHERE ALL(relationship IN relationships(path)
            WHERE NOT (
                elementId(startNode(relationship)) + '|' + elementId(endNode(relationship))
                IN $forbidden_road_pairs
            ))
        RETURN path,
            [n IN nodes(path) | elementId(n)] AS node_ids,
                     [n IN nodes(path) | {lat: n.lat, lon: n.lon, id: coalesce(n.id, elementId(n))}] AS nodes_data,
                     [r IN relationships(path) | {highway: r.highway, surface: r.surface, distance: r.distance,
                         smoothness: r.smoothness, wheelchair: r.wheelchair, incline: r.incline, lit: r.lit}] AS rels_data,
                     reduce(d = 0.0, r IN relationships(path) | d + coalesce(r.distance, 1.0)) AS distance,
                     reduce(c = 0.0, r IN relationships(path) | c + coalesce(r.temp_cost, 1.0)) AS cost
        """

    try:
        print("[Routing Agent Node] Updating edge preference costs...")
        execute_cypher_query(graph_service, update_costs_cypher, {})

        route_mode = route_request.get("route_type", "loop")
        print(f"[Routing Agent Node] ACTIVE ROUTING CODE: {route_mode}")
        print(f"[Routing Agent Node] Searching waypoints for target {target_km:.1f} km...")
        waypoints = execute_cypher_query(graph_service, find_waypoints_cypher, {
            "start_node_id": str(start_node_id),
            "end_node_id": str(end_node_id),
            "target_m": float(target_km) * 1000.0,
        })
        print(f"[Routing Agent Node] Waypoint candidates found: {len(waypoints or [])}")

        if waypoints:
            random.shuffle(waypoints)
            evaluated_routes = []

            candidate_limit = 25 if route_request.get("route_type") == "loop" else 80
            for candidate in waypoints[:candidate_limit]:
                wp_id = candidate["waypoint_id"]
                
                # Execute Leg 1: Start -> Waypoint
                leg1_res = execute_cypher_query(graph_service, leg1_cypher, {
                    "start_id": str(start_node_id),
                    "waypoint_id": str(wp_id)
                })

                if not leg1_res or not leg1_res[0]:
                    continue

                leg1_nodes_ids = leg1_res[0]["node_ids"]
                # Exclude destination node of leg 1 to allow continuation
                forbidden = leg1_nodes_ids[:-1]
                forbidden_relationships = leg1_res[0].get("relationship_ids", [])
                forbidden_road_pairs = []
                for road_pair in leg1_res[0].get("road_pairs", []):
                    forbidden_road_pairs.extend((road_pair["forward"], road_pair["reverse"]))

                # Execute Leg 2: Waypoint -> End
                leg2_params = {
                    "waypoint_id": str(wp_id),
                    "end_id": str(end_node_id),
                    "forbidden_nodes": forbidden,
                    "forbidden_relationships": forbidden_relationships,
                    "forbidden_road_pairs": forbidden_road_pairs,
                    "allow_overlap": False,
                }
                if route_request.get("route_type") == "loop":
                    # Loop return legs must not reuse outbound internal nodes.
                    leg2_res = execute_cypher_query(
                        graph_service, leg2_loop_no_backtrack_cypher, leg2_params
                    )
                else:
                    leg2_res = execute_cypher_query(
                        graph_service, leg2_disjoint_cypher, leg2_params
                    )

                if not leg2_res or not leg2_res[0]:
                    continue

                total_dist = leg1_res[0]["distance"] + leg2_res[0]["distance"]
                total_cost = leg1_res[0]["cost"] + leg2_res[0]["cost"]
                dist_km = total_dist / 1000.0
                dist_diff = abs(dist_km - target_km)

                combined_path_nodes = leg1_res[0]["nodes_data"] + leg2_res[0]["nodes_data"][1:]
                combined_edge_details = leg1_res[0]["rels_data"] + leg2_res[0]["rels_data"]

                formatted_route = [{
                    "path_nodes": combined_path_nodes,
                    "edge_details": combined_edge_details,
                    "totalDistance": total_dist,
                    "totalCost": total_cost
                }]

                evaluated_routes.append((dist_diff, dist_km, formatted_route))

            if evaluated_routes:
                evaluated_routes.sort(key=lambda x: x[0])

                for diff, dist_km, route in evaluated_routes:
                    if (target_km - 2.0) <= dist_km <= (target_km + 2.0):
                        print(f"[Routing Agent Node] Target route found (No Backtracking): {dist_km:.2f} km")
                        return {
                            "start_node_id": start_node_id,
                            "end_node_id": end_node_id,
                            "raw_route_data": route,
                            "is_valid": True
                        }

                best_diff, best_dist_km, best_route = evaluated_routes[0]
                print(f"[Routing Agent Node] Selected closest non-backtracking route: {best_dist_km:.2f} km")
                return {
                    "start_node_id": start_node_id,
                    "end_node_id": end_node_id,
                    "raw_route_data": best_route,
                    "is_valid": True
                }

    except Exception as e:
        print(f"[Routing Agent Node] Cypher execution failed: {e}")

    return {
        "start_node_id": start_node_id,
        "end_node_id": end_node_id,
        "raw_route_data": None, 
        "is_valid": False, 
        "error_message": "Routing failed to generate a non-backtracking route within tolerance."
    }