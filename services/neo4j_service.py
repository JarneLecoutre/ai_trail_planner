# ----------------------------------------------------------
# NEO4J DATABASE CONNECTIONS AND CYPHER QUERY FUNCTIONS
# ----------------------------------------------------------

import time

from neo4j.exceptions import ClientError, ServiceUnavailable, SessionExpired
from langchain_neo4j import Neo4jGraph

class Neo4jService:
    def __init__(self, uri, username, password, database=None, retries=3):
        if not uri or not username or not password:
            raise ValueError(
                "Neo4j configuration is incomplete. Set NEO4j_URI, "
                "NEO4j_USERNAME, and NEO4j_PASSWORD in .env."
            )

        database = (database or "neo4j").strip()
        last_error = None

        for attempt in range(1, retries + 1):
            try:
                self.graph = Neo4jGraph(
                    url=uri,
                    username=username,
                    password=password,
                    database=database,
                )
                print(f"[Neo4j] Connected to Aura database '{database}'.")
                return
            except ClientError as error:
                message = str(error)
                if "DatabaseNotFound" in message:
                    raise RuntimeError(
                        f"Neo4j database '{database}' was not found. "
                        "Check that NEO4j_DATABASE matches the database configured in Aura."
                    ) from error
                last_error = error
            except (ServiceUnavailable, SessionExpired, OSError) as error:
                last_error = error

            if attempt < retries:
                delay = attempt * 2
                print(
                    f"[Neo4j] Connection attempt {attempt}/{retries} failed: "
                    f"{last_error}. Retrying in {delay}s..."
                )
                time.sleep(delay)

        raise RuntimeError(
            f"Could not connect to Neo4j Aura after {retries} attempts. "
            "Check the Aura instance state, URI, credentials, and network."
        ) from last_error

    def get_closest_node_id(self, cl_lat: float, cl_lon: float) -> str:
        """
        Finds the closest OSMNode using the pre-computed spatial point index
        """
        query = """
        MATCH (n:OSMNode)
        WHERE n.location IS NOT NULL
        
        WITH n, point.distance(
            n.location, 
            point({latitude: $cl_lat, longitude: $cl_lon})
        ) AS dist
        
        ORDER BY dist ASC
        LIMIT 1
        RETURN elementId(n) AS nodeId, n.id AS osmId, dist
        """   

        result = self.graph.query(
            query,
            params={
                "cl_lat": cl_lat,
                "cl_lon": cl_lon
            }
        )

        if result:
            closest_dist = round(result[0]["dist"], 2)
            print(f"Success: Closest OSMNode found at {closest_dist} meters from current location.")
            return result[0]["nodeId"]

        print("Warning: No close OSMNode found matching the criteria.")
        return None     