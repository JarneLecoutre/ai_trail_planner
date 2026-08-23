from utils.map_generator import create_map_from_neo4j_output
from pathlib import Path

def validator_node(state: dict) -> dict:
    print("--- [Validator Node] Inspecting structural data integrity ---")
    raw_data = state.get("raw_route_data")
    
    if not raw_data:
        print("[Validator Node] Verification failed: Empty dataset retrieved.")
        return {
            "is_valid": False,
            "error_message": "Empty network response.",
            "retry_count": state["retry_count"] + 1
        }

    route_type = state.get("route_request", {}).get("route_type", "loop")
    map_output_name = state.get("map_output_name", "route_map.html")
    map_output_path = state.get("map_output_path") or str(Path("output") / map_output_name)
    success = create_map_from_neo4j_output(
        raw_data, map_output_path, route_type=route_type
    )
    
    if not success:
        print("[Validator Node] Verification failed: Map generator could not structure the route.")
        return {
            "is_valid": False,
            "error_message": "Route rendering failed.",
            "retry_count": state["retry_count"] + 1
        }

    print("[Validator Node] Success: Integrity check passed.")
    return {"is_valid": True, "error_message": None}

def evaluate_routing_condition(state: dict) -> str:
    if state["is_valid"]:
        return "route_accepted"
    else:
        if state["retry_count"] >= 3:
            print("[GraphRouter] Aborting cycle execution: Maximum trial threshold reached.")
            return "max_failures_abort"
        print(f"[GraphRouter] Routing state invalid. Triggering self-correction loop execution step.")
        return "trigger_recalculation"