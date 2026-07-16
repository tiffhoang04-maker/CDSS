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

    def get_differential_diagnoses(
        self,
        symptom_terms: list[str],
        context_terms: list[str],
        limit: int = 10
    ) -> list[dict[str, Any]]:
        """Rank graph candidates by explicit symptom and context overlap."""

        query = """
        CALL () {
          WITH $symptom_terms AS symptom_terms
          UNWIND symptom_terms AS term
          MATCH (d:Disease)-[:PRESENTS_DpS]-(s:Symptom)
          WHERE size(term) >= 3 AND (
            toLower(coalesce(s.name, "")) CONTAINS term
            OR term CONTAINS toLower(coalesce(s.name, ""))
          )
          WITH
            d,
            collect(DISTINCT term) AS matched_patient_terms,
            collect(DISTINCT s.name) AS matched_symptoms
          WHERE size(matched_patient_terms) >= 2
          RETURN
            coalesce(d.identifier, elementId(d)) AS diagnosis_id,
            d.name AS diagnosis_name,
            labels(d) AS node_labels,
            matched_symptoms,
            matched_patient_terms,
            [] AS matched_context_terms,
            size(matched_patient_terms) * 10 AS graph_score,
            "PRESENTS_DpS symptom overlap" AS ranking_basis

          UNION

          WITH
            $symptom_terms AS symptom_terms,
            $context_terms AS context_terms
          MATCH (c:Condition)
          OPTIONAL MATCH (c)-[:MAPSTO_CmS]-(s:Symptom)
          WITH
            c,
            symptom_terms,
            context_terms,
            collect(DISTINCT s.name) AS graph_symptom_names
          WITH
            c,
            [name IN graph_symptom_names
              WHERE name IS NOT NULL AND any(term IN symptom_terms WHERE
                size(term) >= 3 AND (
                  toLower(name) CONTAINS term
                  OR term CONTAINS toLower(name)
                )
              )
            ] AS matched_symptoms,
            [term IN symptom_terms
              WHERE any(name IN graph_symptom_names WHERE
                name IS NOT NULL AND size(term) >= 3 AND (
                  toLower(name) CONTAINS term
                  OR term CONTAINS toLower(name)
                )
              )
            ] AS matched_patient_terms,
            [term IN context_terms
              WHERE size(term) >= 4
                AND toLower(coalesce(c.name, "")) CONTAINS term
            ] AS matched_context_terms
          WHERE
            size(matched_symptoms) > 0
            OR size(matched_context_terms) > 0
          RETURN
            coalesce(c.identifier, elementId(c)) AS diagnosis_id,
            c.name AS diagnosis_name,
            labels(c) AS node_labels,
            matched_symptoms,
            matched_patient_terms,
            matched_context_terms,
            size(matched_patient_terms) * 10
              + size(matched_context_terms) * 50 AS graph_score,
            "Condition context or MAPSTO_CmS overlap" AS ranking_basis
        }
        RETURN
          diagnosis_id,
          diagnosis_name,
          node_labels,
          matched_symptoms,
          matched_patient_terms,
          matched_context_terms,
          graph_score,
          ranking_basis
        ORDER BY graph_score DESC, diagnosis_name
        LIMIT $limit
        """

        return self.run_query(
            query,
            {
                "symptom_terms": symptom_terms,
                "context_terms": context_terms,
                "limit": limit
            }
        )

    def get_diagnosis_evidence(
        self,
        diagnosis_id: str,
        symptom_terms: list[str]
    ) -> list[dict[str, Any]]:
        """Return graph symptoms attached to an exact diagnosis identifier."""

        query = """
        MATCH (d)
        WHERE (d:Condition OR d:Disease)
          AND coalesce(d.identifier, elementId(d)) = $diagnosis_id
        OPTIONAL MATCH (d)-[r]-(s:Symptom)
        WHERE type(r) IN ["PRESENTS_DpS", "MAPSTO_CmS"]
        WITH d, collect(DISTINCT CASE WHEN s IS NULL THEN null ELSE {
          symptom_id: coalesce(s.identifier, elementId(s)),
          symptom_name: s.name,
          relationship: type(r),
          matches_patient_terms: any(term IN $symptom_terms WHERE
            size(term) >= 3 AND (
              toLower(coalesce(s.name, "")) CONTAINS term
              OR term CONTAINS toLower(coalesce(s.name, ""))
            )
          )
        } END) AS raw_symptoms
        RETURN
          coalesce(d.identifier, elementId(d)) AS diagnosis_id,
          d.name AS diagnosis_name,
          labels(d) AS node_labels,
          [item IN raw_symptoms WHERE item IS NOT NULL] AS graph_symptoms
        """

        return self.run_query(
            query,
            {
                "diagnosis_id": diagnosis_id,
                "symptom_terms": symptom_terms
            }
        )

    def get_recommended_tests(
        self,
        diagnosis_id: str,
        limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return graph actions connected to a diagnosis as diagnostic tests."""

        query = """
        MATCH (d)
        WHERE (d:Condition OR d:Disease)
          AND coalesce(d.identifier, elementId(d)) = $diagnosis_id
        CALL (d) {
          MATCH (d)-[:DIAGNOSES_AdC]-(a:Action)
          RETURN a, d AS graph_condition

          UNION

          MATCH (d)-[:MAPSTO_CmD]-(c:Condition)
                -[:DIAGNOSES_AdC]-(a:Action)
          RETURN a, c AS graph_condition
        }
        RETURN DISTINCT
          coalesce(a.identifier, elementId(a)) AS test_id,
          coalesce(a.phrase, a.name) AS label,
          a.name AS name,
          a.phrase AS phrase,
          properties(a) AS properties,
          coalesce(graph_condition.identifier, elementId(graph_condition))
            AS graph_condition_id,
          graph_condition.name AS graph_condition_name,
          "DIAGNOSES_AdC" AS relationship,
          labels(a) AS node_labels
        ORDER BY label
        LIMIT $limit
        """

        return self.run_query(
            query,
            {"diagnosis_id": diagnosis_id, "limit": limit}
        )

    def get_resource(self, resource_id: str) -> list[dict[str, Any]]:
        """Look up one exact Action or MedKit resource identifier."""

        query = """
        MATCH (resource)
        WHERE (resource:Action OR resource:MedKit)
          AND coalesce(resource.identifier, elementId(resource)) = $resource_id
        RETURN
          coalesce(resource.identifier, elementId(resource)) AS resource_id,
          coalesce(resource.name, resource.phrase) AS resource_name,
          labels(resource) AS node_labels,
          properties(resource) AS properties
        """

        return self.run_query(query, {"resource_id": resource_id})

    def explain_recommendation(
        self,
        diagnosis_id: str,
        recommendation_id: str
    ) -> list[dict[str, Any]]:
        """Return short, whitelisted graph paths supporting a recommendation."""

        query = """
        MATCH (diagnosis)
        WHERE (diagnosis:Condition OR diagnosis:Disease)
          AND coalesce(diagnosis.identifier, elementId(diagnosis))
            = $diagnosis_id
        WITH diagnosis
        MATCH (recommendation)
        WHERE (recommendation:Action OR recommendation:MedKit)
          AND coalesce(recommendation.identifier, elementId(recommendation))
            = $recommendation_id
        MATCH path = (diagnosis)-[*1..2]-(recommendation)
        WHERE all(rel IN relationships(path) WHERE type(rel) IN [
          "DIAGNOSES_AdC",
          "TREATS_MKtC",
          "ASSISTSTREATMENT_MKaC",
          "ASSISTSTREATMENT_AaC",
          "MAPSTO_CmD",
          "INCLUDES_MKiMK"
        ])
        RETURN DISTINCT
          [node IN nodes(path) | {
            node_id: coalesce(node.identifier, elementId(node)),
            name: coalesce(node.name, node.phrase),
            labels: labels(node)
          }] AS nodes,
          [rel IN relationships(path) | type(rel)] AS relationships
        ORDER BY size(relationships)
        LIMIT 10
        """

        return self.run_query(
            query,
            {
                "diagnosis_id": diagnosis_id,
                "recommendation_id": recommendation_id
            }
        )
