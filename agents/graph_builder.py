from typing import TypedDict, List, Optional, Any
from langgraph.graph import StateGraph, END

from agents.intent_parser import intent_parser_node
from agents.orchestrator import orchestrator_node
from agents.routing import routing_node
from agents.validator import validator_node, evaluate_routing_condition

class SearchState(TypedDict):
    user_request: str
    map_output_name: str
    map_output_path: Optional[str]
    distance_km: float
    start_lat: Optional[float]
    start_lon: Optional[float]
    end_lat: Optional[float]
    end_lon: Optional[float]
    start_node_id: Optional[str]
    end_node_id: Optional[str]
    route_request: Optional[dict]
    generated_cypher: Optional[str]
    constraints: dict 
    raw_route_data: Optional[List[dict]]
    is_valid: bool
    error_message: Optional[str]
    retry_count: int
    final_narrative: Optional[str]
    _llm: Any 
    _graph_service: Any

workflow = StateGraph(SearchState)

workflow.add_node("intent", intent_parser_node)
workflow.add_node("orchestrator", orchestrator_node)
workflow.add_node("router", routing_node)
workflow.add_node("validator", validator_node)

workflow.set_entry_point("intent")
workflow.add_edge("intent", "orchestrator")
workflow.add_edge("router", "validator")

def should_exit_after_orchestrator(state: dict) -> str:
    if state.get("final_narrative"):
        return "end_summary"
    return "continue_loop"

workflow.add_conditional_edges(
    "orchestrator",
    should_exit_after_orchestrator,
    {
        "end_summary": END,
        "continue_loop": "router"
    }
)

workflow.add_conditional_edges(
    "validator",
    evaluate_routing_condition,
    {
        "route_accepted": "orchestrator",
        "trigger_recalculation": "orchestrator",
        "max_failures_abort": END
    }
)

compiled_agent_graph = workflow.compile()