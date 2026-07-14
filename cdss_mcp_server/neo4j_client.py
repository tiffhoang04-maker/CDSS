# this script uses the regular Neo4j driver instead of Graph Data Science (GDS)
# hopefully it'll be lighter and simpler to debug for later
import os
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase


load_dotenv()


class Neo4jClient:
    def __init__(self) -> None:
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.username = os.getenv("NEO4J_USERNAME", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD")
        self.database = os.getenv("NEO4J_DATABASE", "exmc")

        if not self.password:
            raise ValueError("NEO4J_PASSWORD is missing from .env")
        # whoever takes this over can just input their own pw and reference their own dbms from neo4j desktop!

        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.username, self.password)
        )

    def close(self) -> None:
        self.driver.close()

    def run_query(
        self,
        query: str,
        params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        params = params or {}

        with self.driver.session(database=self.database) as session:
            result = session.run(query, params)
            return [dict(record) for record in result]

    def get_stage_actions(
        self,
        stage: str,
        terms: list[str] | None = None,
        medkit_option_ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """
        Return valid KG action options for a stage.

        This mirrors Charlotte's old stage buckets:
        - Initial Assessment Stage: Action nodes with early_action = true
        - Diagnosis/Differential: Action nodes with is_action = true and phrase
        - Monitoring: Action nodes with general_monitor = true
        - Treatment/Intervention: MedKit nodes connected to Conditions
        """

        if stage == "Initial Assessment Stage":
            # was originally too broad
            # here i pass scenario seed terms into the query and prefer actions whose name/phrase matches wound (or whatever medical condition) related terms
            query = """
            MATCH (n:Action {early_action: true})
            WHERE any(term IN $terms WHERE 
                toLower(coalesce(n.name, "")) CONTAINS toLower(term)
                OR toLower(coalesce(n.phrase, "")) CONTAINS toLower(term)
                )
            RETURN DISTINCT
              coalesce(n.identifier, elementId(n)) AS option_id,
              coalesce(n.phrase, n.name) AS label,
              n.name AS name,
              n.phrase AS phrase,
              labels(n) AS node_labels
            ORDER BY label
            """
            return self.run_query(query, {"terms": terms or []})

        if stage in ["Diagnosis Stage", "Differential Diagnosis Stage"]:
            query = """
            MATCH (n:Action {is_action: true})
            WHERE n.phrase IS NOT NULL
            RETURN DISTINCT
              coalesce(n.identifier, elementId(n)) AS option_id,
              coalesce(n.phrase, n.name) AS label,
              n.name AS name,
              n.phrase AS phrase,
              labels(n) AS node_labels
            ORDER BY label
            """
            return self.run_query(query)

        if stage == "Reevaluation Stage":
            query = """
            MATCH (n:Action {general_monitor: true})
            RETURN DISTINCT
              coalesce(n.identifier, elementId(n)) AS option_id,
              coalesce(n.phrase, n.name) AS label,
              n.name AS name,
              n.phrase AS phrase,
              labels(n) AS node_labels
            ORDER BY label
            """
            return self.run_query(query)

        if stage == "Treatment Stage":
            query = """
            MATCH (m:MedKit)
            WHERE (
              size($medkit_option_ids) > 0
              AND m.identifier IN $medkit_option_ids
            ) OR (
              size($medkit_option_ids) = 0
              AND EXISTS { MATCH (:Condition)-[:TREATS_MKtC]-(m) }
            )
            RETURN DISTINCT
              coalesce(m.identifier, elementId(m)) AS option_id,
              m.name AS label,
              m.name AS name,
              m.route_of_use AS route_of_use,
              m.strength_volume AS strength_volume,
              m.location AS location,
              m.qty_in_pack AS qty_in_pack,
              labels(m) AS node_labels
            ORDER BY label
            """
            return self.run_query(
                query,
                {"medkit_option_ids": medkit_option_ids or []}
            )

        return []

    def get_context_by_seed_terms(
        self,
        symptoms: list[str],
        conditions: list[str],
        diseases: list[str],
        limit: int = 50
    ) -> list[dict[str, Any]]:
        """
        Retrieve simple KG context around scenario seed terms.
        This is intentionally read-only and conservative.
        """

        query = """
        WITH $terms AS terms
        MATCH (n)
        WHERE any(term IN terms WHERE
          toLower(coalesce(n.name, "")) CONTAINS toLower(term)
          OR toLower(coalesce(n.phrase, "")) CONTAINS toLower(term)
          OR toLower(coalesce(n.identifier, "")) CONTAINS toLower(term)
        )
        OPTIONAL MATCH (n)-[r]-(neighbor)
        RETURN DISTINCT
          labels(n) AS source_labels,
          coalesce(n.name, n.phrase, n.identifier) AS source_name,
          type(r) AS relationship,
          labels(neighbor) AS neighbor_labels,
          coalesce(neighbor.name, neighbor.phrase, neighbor.identifier) AS neighbor_name
        LIMIT $limit
        """

        terms = symptoms + conditions + diseases

        return self.run_query(
            query,
            {
                "terms": terms,
                "limit": limit
            }
        )
