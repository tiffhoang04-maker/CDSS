import unittest
from unittest.mock import patch

import simple_server


class SimpleServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = {
            "patient_id": "patient",
            "scenario_id": "scenario",
            "clinical_data": {
                "chief_complaint": {
                    "value": "Severe headache and ataxia",
                    "status": "known",
                }
            },
        }
        self.scenario = {
            "scenario_id": "scenario",
            "setting": {"environment": "high altitude"},
            "kg_seed_terms": {"symptoms": ["faintness"]},
        }

    def test_case_terms_include_recorded_observations(self) -> None:
        symptom_terms, context_terms = simple_server._get_case_terms(
            self.state,
            self.scenario,
        )

        self.assertIn("headache", symptom_terms)
        self.assertIn("ataxia", symptom_terms)
        self.assertIn("faintness", symptom_terms)
        self.assertIn("altitude", context_terms)

    @patch.object(simple_server, "save_observation")
    def test_record_observation_has_no_checklist_gate(self, save) -> None:
        save.return_value = {"value": "New finding", "status": "known"}

        result = simple_server.record_observation(
            "custom_finding",
            "New finding",
        )

        self.assertTrue(result["accepted"])
        self.assertEqual(save.call_args.kwargs["field_id"], "custom_finding")

    @patch.object(simple_server, "neo4j_client")
    @patch.object(simple_server, "read_scenario")
    @patch.object(simple_server, "read_patient_state")
    def test_differential_uses_recorded_terms(
        self,
        read_state,
        read_scenario,
        client,
    ) -> None:
        read_state.return_value = self.state
        read_scenario.return_value = self.scenario
        client.get_differential_diagnoses.return_value = [{
            "diagnosis_id": "DX:1",
            "diagnosis_name": "Example",
        }]

        result = simple_server.get_differential(limit=5)

        self.assertEqual(result["candidate_count"], 1)
        call = client.get_differential_diagnoses.call_args.kwargs
        self.assertIn("headache", call["symptom_terms"])
        self.assertEqual(call["limit"], 5)


if __name__ == "__main__":
    unittest.main()
