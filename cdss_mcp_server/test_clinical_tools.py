import unittest
from unittest.mock import patch

import cdss_mcp_server.project_build.server_legacy as server_legacy


class ClinicalToolTests(unittest.TestCase):
    @patch.object(server_legacy, "neo4j_client")
    def test_get_differential_diagnoses(self, client) -> None:
        client.get_differential_diagnoses.return_value = [{
            "diagnosis_id": "ExMCcondition:90",
            "diagnosis_name": "Altitude Sickness",
            "graph_score": 50
        }]

        result = server_legacy.get_differential_diagnoses(limit=10)

        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(
            result["candidates"][0]["diagnosis_id"],
            "ExMCcondition:90"
        )
        call = client.get_differential_diagnoses.call_args.kwargs
        self.assertIn("headache", call["symptom_terms"])
        self.assertIn("altitude", call["context_terms"])

    @patch.object(server_legacy, "neo4j_client")
    def test_get_diagnosis_evidence(self, client) -> None:
        client.get_diagnosis_evidence.return_value = [{
            "diagnosis_id": "DOID:test",
            "diagnosis_name": "Test disease",
            "node_labels": ["Disease"],
            "graph_symptoms": [{
                "symptom_id": "SYM:1",
                "symptom_name": "Headache",
                "relationship": "PRESENTS_DpS",
                "matches_patient_terms": True
            }]
        }]

        result = server_legacy.get_diagnosis_evidence("DOID:test")

        self.assertTrue(result["found"])
        self.assertEqual(result["evidence_status"], "graph_symptom_overlap")
        self.assertEqual(len(result["supporting_graph_symptoms"]), 1)

    @patch.object(server_legacy, "neo4j_client")
    def test_get_recommended_tests(self, client) -> None:
        client.get_recommended_tests.return_value = [{
            "test_id": "ExMCaction:102",
            "name": "oxygen saturation"
        }]
        client.get_resource.return_value = [{
            "resource_id": "ExMCaction:102",
            "resource_name": "oxygen saturation",
            "node_labels": ["Action"],
            "properties": {}
        }]

        result = server_legacy.get_recommended_tests("ExMCcondition:90")

        self.assertEqual(result["test_count"], 1)
        availability = result["recommended_tests"][0][
            "resource_availability"
        ]
        self.assertEqual(
            availability["availability"],
            "graph_defined_availability_not_verified"
        )

    @patch.object(server_legacy, "neo4j_client")
    def test_check_resource_availability(self, client) -> None:
        client.get_resource.return_value = [{
            "resource_id": "ExMCmedkit:178",
            "resource_name": "Acetazolamide (Diamox)",
            "node_labels": ["MedKit"],
            "properties": {}
        }]

        result = server_legacy.check_resource_availability("ExMCmedkit:178")

        self.assertTrue(result["is_available"])
        self.assertEqual(
            result["availability_source"],
            "scenario_medkit_inventory"
        )

    @patch.object(server_legacy, "neo4j_client")
    def test_explain_recommendation(self, client) -> None:
        client.explain_recommendation.return_value = [{
            "nodes": [],
            "relationships": ["TREATS_MKtC"]
        }]
        client.get_resource.return_value = [{
            "resource_id": "ExMCmedkit:178",
            "resource_name": "Acetazolamide (Diamox)",
            "node_labels": ["MedKit"],
            "properties": {}
        }]

        result = server_legacy.explain_recommendation(
            "ExMCmedkit:178",
            "ExMCcondition:90"
        )

        self.assertTrue(result["supported_by_graph"])
        self.assertIn(
            "treating the Condition",
            result["relationship_explanations"][0]
        )


if __name__ == "__main__":
    unittest.main()
