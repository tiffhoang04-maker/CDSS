# here lives graph-specific query methods
# as of 07/27: i am going to implement only the functions needed for differential diagnosis

from __future__ import annotations
from typing import Any
from .neo4j_client import Neo4jClient

CONDITION_ALIASES: dict[str, str] = {
        "acute mountain sickness": "altitude sickness",
        "ams": "altitude sickness",
        "high-altitude cerebral edema": "altitude sickness",
        "high altitude cerebral edema": "altitude sickness",
        "hace": "altitude sickness",
        "high-altitude pulmonary edema": "altitude sickness",
        "high altitude pulmonary edema": "altitude sickness",
        "hape": "altitude sickness",
    }

class ClinicalKnowledgeRepo:
    def __init__(self, client: Neo4jClient) -> None:
        self.client = client

    def find_differential_candidates(
        self,
        symptom_terms: list[str],
        context_terms: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return one ranked shortlist containing Diseases and Conditions."""
        normalized_symptoms = sorted({
            term.lower().strip()
            for term in symptom_terms
            if term.strip()
        })
        normalized_context = sorted({
            term.lower().strip()
            for term in (context_terms or [])
            if term.strip()
        })

        if not normalized_symptoms and not normalized_context:
            return []
        disease_query = """
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

        WHERE matched_count >= $minimum_disease_matches

        RETURN
            coalesce(d.identifier, elementId(d)) AS candidate_id,
            d.name AS candidate_name,
            "Disease" AS candidate_type,
            matched_symptoms,
            [] AS matched_context,
            matched_count,
            0 AS matched_context_count,
            total_symptoms,
            toFloat(matched_count) / total_symptoms AS match_score,
            matched_count = total_symptoms AS matches_all,
            matched_count * 10 AS graph_score,
            "PRESENTS_DpS symptom overlap" AS provenance

        ORDER BY
            matches_all DESC,
            match_score DESC,
            candidate_name;
        """

        condition_query = """
        WITH
            [term IN $symptom_terms | toLower(trim(term))]
                AS normalized_symptoms,
            [term IN $context_terms | toLower(trim(term))]
                AS normalized_context

        MATCH (c:Condition)
        OPTIONAL MATCH (c)-[:MAPSTO_CmS]-(s:Symptom)

        WITH
            c,
            normalized_symptoms,
            normalized_context,
            [
                symptom_name IN collect(
                    DISTINCT toLower(trim(s.name))
                )
                WHERE symptom_name IN normalized_symptoms
            ] AS matched_symptoms

        WITH
            c,
            normalized_symptoms,
            matched_symptoms,
            [
                term IN normalized_context
                WHERE toLower(coalesce(c.name, "")) CONTAINS term
            ] AS matched_context

        WHERE
            size(matched_symptoms) > 0
            OR size(matched_context) > 0

        WITH
            c,
            normalized_symptoms,
            matched_symptoms,
            matched_context,
            size(matched_symptoms) AS matched_count,
            size(matched_context) AS matched_context_count,
            size(normalized_symptoms) AS total_symptoms

        RETURN
            coalesce(c.identifier, elementId(c)) AS candidate_id,
            c.name AS candidate_name,
            "Condition" AS candidate_type,
            matched_symptoms,
            matched_context,
            matched_count,
            matched_context_count,
            total_symptoms,
            CASE
                WHEN total_symptoms = 0 THEN 0.0
                ELSE toFloat(matched_count) / total_symptoms
            END AS match_score,
            total_symptoms > 0
                AND matched_count = total_symptoms AS matches_all,
            matched_count * 10 + matched_context_count * 50
                AS graph_score,
            "MAPSTO_CmS symptom or Condition context overlap"
                AS provenance

        ORDER BY
            graph_score DESC,
            candidate_name;
        """

        diseases = self.client.run_query(
            disease_query,
            {
                "symptom_terms": normalized_symptoms,
                "minimum_disease_matches": (
                    2 if len(normalized_symptoms) > 1 else 1
                ),
            }
        )

        conditions = self.client.run_query(
            condition_query,
            {
                "symptom_terms": normalized_symptoms,
                "context_terms": normalized_context,
            },
        )

        candidates = {
            (
                candidate.get("candidate_type"),
                candidate.get("candidate_id"),
            ): candidate
            for candidate in [*diseases, *conditions]
        }

        safe_limit = max(1, min(int(limit), 50))

        return sorted(
            candidates.values(),
            key=lambda candidate: (
                -int(candidate.get("graph_score", 0)),
                -int(bool(candidate.get("matches_all", False))),
                -int(candidate.get("matched_count", 0)),
                str(candidate.get("candidate_name", "")).lower(),
                str(candidate.get("candidate_id", "")),
            ),
        )[:safe_limit]

    # this is here because some cases are not "disease" nodes but are "condition" nodes
    def find_candidate_by_name(
        self,
        candidate_name: str,
    ) -> dict[str, Any] | None:
        """
        Search Disease first. Search Condition only when no exact Disease
        name matches.
        """
        normalized_name = candidate_name.strip().lower()

        if not normalized_name:
            return None

        disease_query = """
        MATCH (candidate:Disease)
        WHERE toLower(trim(candidate.name)) = $candidate_name

        RETURN
            candidate.identifier AS candidate_id,
            candidate.name AS candidate_name,
            "Disease" AS candidate_type

        ORDER BY candidate.identifier
        LIMIT 1
        """

        diseases = self.client.run_query(
            disease_query,
            {"candidate_name": normalized_name},
        )

        if diseases:
            return {
                **diseases[0],
                "resolution_path": "disease_exact_name",
            }

        condition_lookup_name = CONDITION_ALIASES.get(
            normalized_name,
            normalized_name,
        )
        condition_query = """
        MATCH (candidate:Condition)
        WHERE toLower(trim(candidate.name)) = $candidate_name

        RETURN
            candidate.identifier AS candidate_id,
            candidate.name AS candidate_name,
            "Condition" AS candidate_type

        ORDER BY candidate.identifier
        LIMIT 1
        """

        conditions = self.client.run_query(
            condition_query,
            {"candidate_name": condition_lookup_name},
        )

        if conditions:
            used_alias = condition_lookup_name != normalized_name

            return {
                **conditions[0],
                "requested_name": candidate_name,
                "lookup_name": condition_lookup_name,
                "resolution_path": (
                    "condition_controlled_alias"
                    if used_alias
                    else "condition_exact_name_fallback"
                ),
            }

    def find_medkit_treatment_options(
    self,
    candidate_id: str,
    candidate_type: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
        query = """
        MATCH (candidate)
        WHERE candidate.identifier = $candidate_id
        AND $candidate_type IN labels(candidate)

        MATCH (condition:Condition)
        WHERE
            (
                $candidate_type = "Condition"
                AND condition = candidate
            )
            OR (
                $candidate_type = "Disease"
                AND EXISTS {
                    MATCH (condition)-[:MAPSTO_CmD]-(candidate)
                }
            )

        MATCH (medkit:MedKit)
            -[treatment:TREATS_MKtC|ASSISTSTREATMENT_MKaC]-
            (condition)

        OPTIONAL MATCH
            (category:MedKit)-[:INCLUDES_MKiMK]-(medkit)
        WHERE category.is_category = true

        WITH
            candidate,
            condition,
            medkit,
            collect(DISTINCT type(treatment))
                AS treatment_relationships,
            [
                category_data IN collect(DISTINCT {
                    medkit_id: category.identifier,
                    name: category.name
                })
                WHERE category_data.medkit_id IS NOT NULL
            ] AS categories

        RETURN
            medkit.identifier AS medkit_id,
            medkit.name AS name,
            medkit.phrase AS phrase,
            medkit.route_of_use AS route_of_use,
            medkit.strength_volume AS strength_volume,
            medkit.location AS location,
            medkit.qty_in_pack AS qty_in_pack,
            medkit.side_effects AS side_effects,
            medkit.comments AS comments,
            medkit.is_category AS is_category,

            condition.identifier AS condition_id,
            condition.name AS condition_name,

            candidate.identifier AS candidate_id,
            candidate.name AS candidate_name,
            $candidate_type AS candidate_type,

            treatment_relationships,
            categories

        ORDER BY
            toLower(
                coalesce(
                    medkit.name,
                    medkit.phrase,
                    medkit.identifier
                )
            )

        LIMIT $limit
        """

        safe_limit = max(1, min(int(limit), 50))

        return self.client.run_query(
            query,
            {
                "candidate_id": candidate_id,
                "candidate_type": candidate_type,
                "limit": safe_limit,
            },
        )
