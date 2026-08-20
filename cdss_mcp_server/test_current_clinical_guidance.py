import unittest
from unittest.mock import Mock

from cdss_mcp_server.project_build.neo4j_logistics.clinical_guideline_service import (
    ClinicalGuidanceService,
)
from cdss_mcp_server.project_build.neo4j_logistics.clinical_knowledge_repo import (
    ClinicalKnowledgeRepo,
)


class ClinicalKnowledgeRepoTests(unittest.TestCase):
    def test_merges_disease_and_condition_candidates_deterministically(self):
        client = Mock()
        client.run_query.side_effect = [
            [
                {
                    "candidate_id": "DOID:1",
                    "candidate_name": "Example disease",
                    "candidate_type": "Disease",
                    "matched_count": 1,
                    "matches_all": False,
                    "graph_score": 10,
                }
            ],
            [
                {
                    "candidate_id": "ExMCcondition:90",
                    "candidate_name": "Altitude Sickness",
                    "candidate_type": "Condition",
                    "matched_count": 1,
                    "matches_all": False,
                    "graph_score": 60,
                }
            ],
        ]
        repository = ClinicalKnowledgeRepo(client)

        candidates = repository.find_differential_candidates(
            symptom_terms=["ataxia", "hypoxia"],
            context_terms=["altitude"],
        )

        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["candidate_type"], "Condition")
        self.assertEqual(
            candidates[0]["candidate_id"],
            "ExMCcondition:90",
        )
        self.assertEqual(client.run_query.call_count, 2)
        disease_params = client.run_query.call_args_list[0].args[1]
        self.assertEqual(disease_params["minimum_disease_matches"], 2)
        condition_params = client.run_query.call_args_list[1].args[1]
        self.assertEqual(condition_params["context_terms"], ["altitude"])


class ClinicalGuidanceServiceTests(unittest.TestCase):
    def test_case_001_queries_condition_context_and_returns_condition(self):
        repository = Mock()
        repository.find_differential_candidates.return_value = [
            {
                "candidate_id": "ExMCcondition:90",
                "candidate_name": "Altitude Sickness",
                "candidate_type": "Condition",
                "matched_symptoms": ["hypoxia"],
                "matched_context": ["altitude"],
                "matched_count": 1,
                "matched_context_count": 1,
                "total_symptoms": 3,
                "match_score": 1 / 3,
                "matches_all": False,
                "graph_score": 60,
                "provenance": (
                    "MAPSTO_CmS symptom or Condition context overlap"
                ),
            }
        ]
        service = ClinicalGuidanceService(repository)
        patient_state = {
            "clinical_data": {
                "spo2": {
                    "value": 58,
                    "status": "abnormal",
                },
                "coordination": {
                    "value": "Impaired coordination and ataxia",
                    "status": "abnormal",
                },
            }
        }
        public_scenario = {
            "setting": {
                "environment": "remote mountain expedition",
                "current_altitude_m": 4800,
            },
            "presenting_information": {
                "chief_concern": (
                    "Severe headache, dizziness, and difficulty walking"
                ),
            },
        }

        result = service.build_differential(
            patient_state=patient_state,
            public_scenario=public_scenario,
        )

        call = repository.find_differential_candidates.call_args.kwargs
        self.assertEqual(
            call["symptom_terms"],
            ["ataxia", "dizziness", "headache", "hypoxia"],
        )
        self.assertIn("altitude", call["context_terms"])
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(
            result["candidates"][0]["candidate_type"],
            "Condition",
        )


if __name__ == "__main__":
    unittest.main()
