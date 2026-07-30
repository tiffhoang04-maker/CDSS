# here lives graph-specific query methods
# as of 07/27: i am going to implement only the functions needed for differential diagnosis

from __future__ import annotations
from typing import Any
from .neo4j_client import Neo4jClient

class ClinicalKnowledgeRepo:
    def __init__(self, client: Neo4jClient) -> None:
        self.client = client

# retrieve every disease supported by the observed findings
# gpt told me to add a high safety ceiling to prevent na accidental massive query
# but i don't think it will be necessary because the query is already limited by the number of findings
    def find_differential_candidates(
        self,
        symptom_terms: list[str]
    ) -> list[dict[str, Any]]:
        if not symptom_terms:
            return []
# this query retrieves every disease matching at least one symptom, then calculates a "match score" based on how many of the provided symptoms are matched by the disease
        query = """
        WITH [term IN $symptom_terms | toLower(trim(term))] AS normalized_terms

        MATCH (d:Disease)-[:PRESENTS_DpS]-(s:Symptom)
        WHERE toLower(trim(s.name)) IN normalized_terms

        WITH
            d,
            normalized_terms,
            collect(DISTINCT toLower(trim(s.name))) AS matched_symptoms

        WITH
            d,
            normalized_terms,
            matched_symptoms,
            size(matched_symptoms) AS matched_count,
            size(normalized_terms) AS total_symptoms

        RETURN
            coalesce(d.identifier, elementId(d)) AS diagnosis_id,
            d.name AS diagnosis_name,
            matched_symptoms,
            matched_count,
            total_symptoms,
            toFloat(matched_count) / total_symptoms AS match_score,
            matched_count = total_symptoms AS matches_all

        ORDER BY
            matches_all DESC,
            match_score DESC,
            diagnosis_name;
        """

        # for future reference:
        # example: Headache and ataxia are associated with 14 candidate diseases. Ask about fever, recent trauma, focal weakness, onset, and toxic exposure to differentiate them.

        return self.client.run_query(
            query,
            {
                "symptom_terms": [
                    term.lower().strip()
                    for term in symptom_terms
                    if term.strip()
                ],
            }
        )
    
    # this is here because some cases are not "disease" nodes but are "condition" nodes
    def find_condition_candidates(
    self,
    symptom_terms: list[str],
    context_terms: list[str],
) -> list[dict[str, Any]]:
        query = """
        MATCH (c:Condition)

        OPTIONAL MATCH (c)-[:MAPSTO_CmS]-(s:Symptom)
        WHERE toLower(trim(s.name)) IN $symptom_terms

        WITH
            c,
            collect(DISTINCT toLower(trim(s.name))) AS matched_symptoms,
            [
                term IN $context_terms
                WHERE toLower(c.name) CONTAINS term
            ] AS matched_context

        WHERE
            size(matched_symptoms) > 0
            OR size(matched_context) > 0

        RETURN
            c.identifier AS candidate_id,
            c.name AS candidate_name,
            "Condition" AS candidate_type,
            matched_symptoms,
            matched_context,
            size(matched_symptoms) AS matched_symptom_count,
            size(matched_context) AS matched_context_count,
            "Neo4j Condition" AS provenance

        ORDER BY
            matched_context_count DESC,
            matched_symptom_count DESC,
            candidate_name
        """

        return self.client.run_query(
            query,
            {
                "symptom_terms": [
                    term.lower().strip()
                    for term in symptom_terms
                ],
                "context_terms": [
                    term.lower().strip()
                    for term in context_terms
                ],
            },
        )

    def find_medkit_treatment_options(
        self,
        diagnosis_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Return exact MedKit nodes connected to a Disease through an approved
        Condition treatment path.

        This is deliberately a closed-world query. A medically plausible item
        is not returned unless the required Neo4j relationships exist.
        """
        query = """
        MATCH (d:Disease {identifier: $diagnosis_id})
        MATCH (c:Condition)-[:MAPSTO_CmD]-(d)
        MATCH (m:MedKit)-[treats:TREATS_MKtC|ASSISTSTREATMENT_MKaC]-(c)

        OPTIONAL MATCH (category:MedKit)-[:INCLUDES_MKiMK]-(m)
        WHERE category.is_category = true

        WITH
            d,
            c,
            m,
            collect(DISTINCT type(treats)) AS treatment_relationships,
            [
                category_data IN collect(DISTINCT {
                    medkit_id: category.identifier,
                    name: category.name
                })
                WHERE category_data.medkit_id IS NOT NULL
            ] AS categories

        RETURN
            m.identifier AS medkit_id,
            m.name AS name,
            m.phrase AS phrase,
            m.route_of_use AS route_of_use,
            m.strength_volume AS strength_volume,
            m.location AS location,
            m.qty_in_pack AS qty_in_pack,
            m.side_effects AS side_effects,
            m.comments AS comments,
            m.is_category AS is_category,
            c.identifier AS condition_id,
            c.name AS condition_name,
            d.identifier AS diagnosis_id,
            d.name AS diagnosis_name,
            treatment_relationships,
            categories

        ORDER BY
            toLower(coalesce(m.name, m.phrase, m.identifier))
        LIMIT $limit
        """

        safe_limit = max(1, min(int(limit), 50))
        return self.client.run_query(
            query,
            {
                "diagnosis_id": diagnosis_id,
                "limit": safe_limit,
            },
        )
