from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_BUILD = Path(__file__).resolve().parent / "project_build"
sys.path.insert(0, str(PROJECT_BUILD))

import server  # noqa: E402
from neo4j_logistics.clinical_knowledge_repo import (  # noqa: E402
    ClinicalKnowledgeRepo,
)


class MedKitRepositoryTests(unittest.TestCase):
    def test_query_uses_only_approved_treatment_paths(self) -> None:
        client = unittest.mock.Mock()
        client.run_query.return_value = []
        repository = ClinicalKnowledgeRepo(client)

        result = repository.find_medkit_treatment_options(
            "DOID:8337",
            limit=500,
        )

        self.assertEqual(result, [])
        query, params = client.run_query.call_args.args
        self.assertIn("MATCH (m:MedKit)", query)
        self.assertIn("TREATS_MKtC|ASSISTSTREATMENT_MKaC", query)
        self.assertIn("MAPSTO_CmD", query)
        self.assertEqual(params["diagnosis_id"], "DOID:8337")
        self.assertEqual(params["limit"], 50)


class MedKitToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = {
            "working_differential": [
                {
                    "diagnosis_id": "DOID:8337",
                    "diagnosis_name": "appendicitis",
                }
            ]
        }

    @patch.object(server, "knowledge_repo")
    @patch.object(server, "read_patient_state")
    def test_returns_exact_graph_options(
        self,
        read_state,
        repository,
    ) -> None:
        read_state.return_value = self.state
        repository.find_medkit_treatment_options.return_value = [
            {
                "medkit_id": "ExMCmedkit:1",
                "name": "Example item",
                "treatment_relationships": ["TREATS_MKtC"],
            }
        ]

        result = server.get_medkit_treatment_options("DOID:8337")

        self.assertTrue(result["success"])
        self.assertTrue(result["closed_world"])
        self.assertEqual(result["option_count"], 1)
        self.assertEqual(
            result["options"][0]["medkit_id"],
            "ExMCmedkit:1",
        )

    @patch.object(server, "knowledge_repo")
    @patch.object(server, "read_patient_state")
    def test_empty_result_for_unsupported_treatment(
        self,
        read_state,
        repository,
    ) -> None:
        read_state.return_value = self.state
        repository.find_medkit_treatment_options.return_value = []

        result = server.get_medkit_treatment_options("DOID:8337")

        self.assertTrue(result["success"])
        self.assertEqual(result["option_count"], 0)
        self.assertEqual(result["options"], [])
        self.assertIn(
            "No graph-supported MedKit",
            result["model_instruction"],
        )

    @patch.object(server, "knowledge_repo")
    @patch.object(server, "read_patient_state")
    def test_rejects_diagnosis_outside_current_differential(
        self,
        read_state,
        repository,
    ) -> None:
        read_state.return_value = self.state

        result = server.get_medkit_treatment_options("DOID:not-allowed")

        self.assertFalse(result["success"])
        self.assertTrue(result["closed_world"])
        repository.find_medkit_treatment_options.assert_not_called()


if __name__ == "__main__":
    unittest.main()
