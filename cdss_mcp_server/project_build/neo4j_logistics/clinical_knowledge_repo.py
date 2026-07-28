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
