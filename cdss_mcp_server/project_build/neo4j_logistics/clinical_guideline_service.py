from __future__ import annotations
import re
from typing import Any
from .clinical_knowledge_repo import ClinicalKnowledgeRepo

# this layer translates patient state into graph queries
# inspect recorded patient observations
# normalize findings into graph terms
# call the clinical knowledge repo to retrieve candidate diagnoses
# format the result to look nice + structured 
# report unmatched terms

# have it search for similar terms/symptoms instead of mapping

OBSERVATION_TO_KG_TERMS: dict[str, list[str]] = {
    "headache": ["headache"],
    "coordination": ["ataxia"],
    "spo2": ["hypoxia"],
    "shortness_of_breath": ["dyspnea"],
    "abdominal_pain": [
        "abdominal pain",
        "acute pain"
    ],
    "abdominal_exam": ["abdomen, acute"],
    "lung_auscultation": [
        "pulmonary crackles",
        "crackles"
    ],
    "gastrointestinal_symptoms": [
        "nausea",
        "vomiting",
    ],
    "temperature": ["fever"],
    "heart_rate": ["tachycardia"],
}

PRESENTING_FINDING_TERMS: dict[str, str] = {
    "abdominal pain": "abdominal pain",
    "dizziness": "dizziness",
    "headache": "headache",
    "loss of appetite": "loss of appetite",
    "nausea": "nausea",
    "shortness of breath": "dyspnea",
    "vomiting": "vomiting",
}

CONTEXT_STOP_WORDS = {
    "care",
    "clinic",
    "context",
    "current",
    "delayed",
    "environment",
    "expedition",
    "field",
    "limited",
    "remote",
    "setting",
    "supplies",
}

class ClinicalGuidanceService:
    def __init__(
        self,
        repository: ClinicalKnowledgeRepo
    ) -> None:
        self.repository = repository

    def extract_abnormal_terms(
        self,
        patient_state: dict[str, Any]
    ) -> list[str]:
        clinical_data = patient_state.get(
            "clinical_data",
            {}
        )

        terms: set[str] = set()

        for field_id, observation in clinical_data.items():
            status = observation.get("status")

            if status not in {
                "abnormal",
                "known_abnormal"
            }:
                continue

            terms.update(
                OBSERVATION_TO_KG_TERMS.get(
                    field_id,
                    []
                )
            )

        return sorted(terms)

    def extract_presenting_terms(
        self,
        public_scenario: dict[str, Any],
    ) -> list[str]:
        presenting = public_scenario.get("presenting_information", {})
        presenting_text = " ".join(
            str(value).lower()
            for value in presenting.values()
        )

        return sorted({
            graph_term
            for phrase, graph_term in PRESENTING_FINDING_TERMS.items()
            if phrase in presenting_text
        })

    def extract_context_terms(
        self,
        public_scenario: dict[str, Any],
    ) -> list[str]:
        setting = public_scenario.get("setting", {})
        context_parts: list[str] = []

        for key, value in setting.items():
            context_parts.append(str(key).replace("_", " "))
            if isinstance(value, str):
                context_parts.append(value)

        tokens = re.findall(
            r"[a-z][a-z-]{3,}",
            " ".join(context_parts).lower(),
        )
        return sorted({
            token
            for token in tokens
            if token not in CONTEXT_STOP_WORDS
        })

    def build_differential(
        self,
        patient_state: dict[str, Any],
        public_scenario: dict[str, Any]
    ) -> dict[str, Any]:
        symptom_terms = sorted({
            *self.extract_abnormal_terms(patient_state),
            *self.extract_presenting_terms(public_scenario),
        })
        context_terms = self.extract_context_terms(public_scenario)

        if not symptom_terms and not context_terms:
            return {
                "success": True,
                "task": "differential",
                "status": "insufficient_information",
                "query_findings": [],
                "query_context": [],
                "candidate_count": 0,
               # "shortlist_count": 0,
                "needs_more_information": True,
               # "leading_candidate": None,
                "candidates": [],
                "recommended_next_step": {
                "action": "collect_assessment_information",
                "reason": (
                    "No abnormal graph-mappable findings are "
                    "currently available."
                ),
            },
                "limitations": [
                    "No abnormal findings were available "
                    "for knowledge-graph retrieval."
                ],
            }

        candidates = (
            self.repository
            .find_differential_candidates(
                symptom_terms=symptom_terms,
                context_terms=context_terms,
            )
        )

        #number of candidates retrieved from Neo4J
        candidate_count = len(candidates)

        top_candidate = candidates[0] if candidates else None
        runner_up = candidates[1] if len(candidates) > 1 else None

        has_strong_leader = bool(
            top_candidate
            and top_candidate.get("matches_all", False)
            and top_candidate.get("matched_count", 0) >= 2
            and (
                runner_up is None
                or top_candidate.get("matched_count", 0)
                > runner_up.get("matched_count", 0)
            )
        )

# results
        if candidate_count == 0:
            status = "no_graph_matches"
            needs_more_information = True
        elif has_strong_leader:
            status = "focused_differential"
            needs_more_information = False
        else:
            status = "needs_more_information"
            needs_more_information = True


# what the model should do next
        if candidate_count == 0:
            recommended_next_step = {
                "action": "collect_more_information",
                "reason": (
                    "The current findings did not match any "
                    "Disease or Condition candidates in the "
                    "knowledge graph."
                ),
        }
        elif needs_more_information:
            recommended_next_step = {
            "action": "collect_more_information",
            "reason": (
                "The graph-supported differential "
                "remains broad."
            ),
        }
        else:
            recommended_next_step = {
            "action": "review_focused_differential",
            "reason": (
                "The graph-supported differential is "
                "focused enough to review."
            ),
        }

        return {
            "success": True,
            "task": "differential",
            "status": status,
            "query_findings": symptom_terms,
            "query_context": context_terms,
            "candidate_count": candidate_count,
            "needs_more_information": needs_more_information,
            "candidates": candidates,
            "recommended_next_step": recommended_next_step,
            "limitations": [
                "Candidate order reflects graph "
                "evidence overlap, not clinical probability."
            ]
        }
