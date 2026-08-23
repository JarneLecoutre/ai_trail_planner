# --------------------
# MAIN SCRIPT
# --------------------

import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# Import specific classes and fucnctions
from services.neo4j_service import Neo4jService
from agents.graph_builder import compiled_agent_graph

# --------------------
# TRAIL PARAMETERS
# --------------------
# Edit these values, then run: python main.py
USER_REQUEST = "Generate a 10 km hike from my home in Grobbendonk to Herentals. I walking with my grandma in a wheelchair. Mostly in green please"
MAP_OUTPUT_NAME = "Hike_to_Herentals_greener.html"

# Used only when USER_REQUEST does not contain a start location.
START_LAT = 51.191582
START_LON = 4.741064
END_LAT = None
END_LON = None

def main():

    # Load Configuration
    load_dotenv()

    # Create output map if not exists
    os.makedirs("output", exist_ok=True)

    # Initialize Infrastructure Services
    neo4j_service = None

    # Initialize Large Language Model
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        project=os.getenv("GCP_PROJECT_ID"),
        location=os.getenv("GCP_LOCATION"),
        temperature=0.1
    )

    try:
        neo4j_service = Neo4jService(
            uri=os.getenv("NEO4j_URI"),
            username=os.getenv("NEO4j_USERNAME"),
            password=os.getenv("NEO4j_PASSWORD"),
            database=os.getenv("NEO4j_DATABASE", "neo4j")
        )

        # Create initial graph state after the database connection succeeds.
        initial_graph_state = {
            "user_request": USER_REQUEST,
            "map_output_name": MAP_OUTPUT_NAME,
            "start_lat": START_LAT,
            "start_lon": START_LON,
            "end_lat": END_LAT,
            "end_lon": END_LON,
            "retry_count": 0,
            "is_valid": False,
            "raw_route_data": None,
            "final_narrative": None,
            "_llm": llm,
            "_graph_service": neo4j_service
        }

        print("[Main Execution] Invoking compiled Multi-Agent LangGraph processing engine...")
        execution_result = compiled_agent_graph.invoke(initial_graph_state)

        print("\n" + "="*50)
        if execution_result.get("final_narrative"):
            print(execution_result["final_narrative"])
        else:
            print("System Error: Loop limits exceeded without satisfying network metrics.")
        print("="*50)

    finally:
        # Guarantee driver cleanup upon exit or failure
        if neo4j_service is not None and hasattr(neo4j_service, "close"):
            neo4j_service.close()
        elif neo4j_service is not None and hasattr(neo4j_service, "graph") and hasattr(neo4j_service.graph, "_driver"):
            neo4j_service.graph._driver.close()
        if neo4j_service is not None:
            print("[System Cleanup] Closed Neo4j session successfully.")


# -------
# RUN
# -------
if __name__ == "__main__":
    main()