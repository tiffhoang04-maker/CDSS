import unittest
from unittest.mock import patch

import cdss_mcp_server.project_build.server_legacy as server_legacy
import cdss_mcp_server.project_build.state_manager_legacy as state_manager_legacy


class WorkflowToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = {
            "scenario_id": "test_scenario",
            "title": "Altitude test",
            "domain": "high_altitude",
            "setting": {},
            "starting_context": {
                "initial_observations": {
                    "spo2_percent_at_rest": 58,
                    "heart_rate_bpm": 110
                }
            },
            "kg_seed_terms": {"symptoms": ["headache"]}
        }
        self.state = {
            "patient_id": "patient",
            "scenario_id": "test_scenario",
            "current_stage": "Diagnosis Stage",
            "completed_action_ids": ["ExMCaction:102", "ExMCaction:82"],
            "completed_action_labels": [
                "Run vitals to check oxygen saturation.",
                "Run a blood gases test."
            ],
            "current_diagnosis_ids": []
        }

    def test_pending_results_ignore_scenario_spo2(self) -> None:
        pending = server_legacy._get_pending_test_results(self.state, self.scenario)

        self.assertEqual(len(pending), 2)
        self.assertEqual(pending[0]["test_id"], "ExMCaction:102")
        self.assertEqual(pending[0]["field_id"], "spo2")
        self.assertEqual(pending[1]["test_id"], "ExMCaction:82")
        self.assertEqual(pending[1]["field_id"], "blood_gases")

    def test_gap_assessment_ignores_scenario_vitals(self) -> None:
        assessment = server_legacy._assess_information_gaps_internal(
            self.state,
            self.scenario
        )

        self.assertNotIn("spo2", assessment["known_information_fields"])
        self.assertNotIn("heart_rate", assessment["known_information_fields"])
        missing_ids = {
            item["field_id"] for item in assessment["missing_information"]
        }
        self.assertIn("spo2", missing_ids)
        self.assertIn("heart_rate", missing_ids)

    @patch.object(server_legacy, "reassess_patient", return_value={"next": "step"})
    @patch.object(server_legacy, "record_patient_test_result")
    @patch.object(server_legacy, "read_patient_state")
    def test_record_test_result_reassesses(
        self,
        read_state,
        save_result,
        _reassess
    ) -> None:
        read_state.return_value = self.state
        save_result.return_value = {
            "test_id": "ExMCaction:82",
            "field_id": "blood_gases",
            "result": "pH 7.40"
        }

        result = server_legacy.record_test_result(
            "ExMCaction:82",
            "pH 7.40",
            status="normal"
        )

        self.assertTrue(result["accepted"])
        self.assertEqual(result["reassessment"], {"next": "step"})
        self.assertEqual(
            save_result.call_args.kwargs["field_id"],
            "blood_gases"
        )

    @patch.object(server_legacy, "reassess_patient", return_value={"next": "step"})
    @patch.object(server_legacy, "save_clinical_observation")
    @patch.object(server_legacy, "read_scenario")
    @patch.object(server_legacy, "read_patient_state")
    def test_record_clinical_observation_reassesses(
        self,
        read_state,
        read_scenario,
        save_observation,
        _reassess
    ) -> None:
        read_state.return_value = self.state
        read_scenario.return_value = self.scenario
        save_observation.return_value = {
            "value": "Airway open",
            "status": "known"
        }

        result = server_legacy.record_clinical_observation(
            "airway_status",
            "Airway open"
        )

        self.assertTrue(result["accepted"])
        self.assertEqual(result["reassessment"], {"next": "step"})

    @patch.object(state_manager_legacy, "write_patient_state")
    @patch.object(state_manager_legacy, "read_patient_state")
    def test_state_manager_persists_test_and_clinical_result(
        self,
        read_state,
        write_state
    ) -> None:
        state = {}
        read_state.return_value = state

        state_manager_legacy.record_patient_test_result(
            test_id="ExMCaction:82",
            result="pH 7.40",
            field_id="blood_gases",
            status="normal"
        )

        self.assertEqual(
            state["test_results"]["ExMCaction:82"]["result"],
            "pH 7.40"
        )
        self.assertEqual(
            state["clinical_data"]["blood_gases"]["status"],
            "normal"
        )
        write_state.assert_called_once()


if __name__ == "__main__":
    unittest.main()
