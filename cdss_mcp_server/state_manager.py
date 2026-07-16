import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
PATIENT_RECORDS_DIR = BASE_DIR / "patient_records"
SCENARIOS_DIR = BASE_DIR / "scenarios"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_patient_record_path(patient_id: str = "current_patient") -> Path:
    if patient_id == "current_patient":
        return PATIENT_RECORDS_DIR / "current_patient.json"

    return PATIENT_RECORDS_DIR / f"{patient_id}.json"


def read_patient_state(patient_id: str = "current_patient") -> dict[str, Any]:
    return read_json(get_patient_record_path(patient_id))


def write_patient_state(
    state: dict[str, Any],
    patient_id: str = "current_patient"
) -> dict[str, Any]:
    write_json(get_patient_record_path(patient_id), state)
    return state


def read_scenario(scenario_id: str) -> dict[str, Any]:
    return read_json(SCENARIOS_DIR / f"{scenario_id}.json")


def add_completed_action(
    choice_id: str,
    choice_label: str | None = None,
    patient_id: str = "current_patient"
) -> dict[str, Any]:
    state = read_patient_state(patient_id)

    state.setdefault("completed_action_ids", [])
    state.setdefault("completed_action_labels", [])

    if choice_id not in state["completed_action_ids"]:
        state["completed_action_ids"].append(choice_id)

    if choice_label and choice_label not in state["completed_action_labels"]:
        state["completed_action_labels"].append(choice_label)

    return write_patient_state(state, patient_id)


def update_stage(
    new_stage: str,
    patient_id: str = "current_patient"
) -> dict[str, Any]:
    state = read_patient_state(patient_id)
    state["current_stage"] = new_stage
    return write_patient_state(state, patient_id)


def record_clinical_observation(
    field_id: str,
    value: str,
    unit: str = "",
    status: str = "known",
    source: str = "user",
    patient_id: str = "current_patient"
) -> dict[str, Any]:
    state = read_patient_state(patient_id)
    observation = {
        "value": value,
        "status": status,
        "source": source,
        "recorded_at": datetime.now(timezone.utc).isoformat()
    }
    if unit:
        observation["unit"] = unit

    state.setdefault("clinical_data", {})[field_id] = observation
    write_patient_state(state, patient_id)
    return observation


def record_patient_test_result(
    test_id: str,
    result: str,
    field_id: str,
    unit: str = "",
    status: str = "known",
    source: str = "user",
    patient_id: str = "current_patient"
) -> dict[str, Any]:
    state = read_patient_state(patient_id)
    test_result = {
        "test_id": test_id,
        "field_id": field_id,
        "result": result,
        "status": status,
        "source": source,
        "recorded_at": datetime.now(timezone.utc).isoformat()
    }
    if unit:
        test_result["unit"] = unit

    state.setdefault("test_results", {})[test_id] = test_result
    state.setdefault("clinical_data", {})[field_id] = {
        "value": result,
        "status": status,
        "source": f"test:{test_id}",
        "recorded_at": test_result["recorded_at"],
        **({"unit": unit} if unit else {})
    }
    write_patient_state(state, patient_id)
    return test_result


def record_patient_diagnosis(
    diagnosis_id: str,
    diagnosis_name: str,
    evidence_summary: str = "",
    patient_id: str = "current_patient"
) -> dict[str, Any]:
    state = read_patient_state(patient_id)
    diagnosis = {
        "diagnosis_id": diagnosis_id,
        "diagnosis_name": diagnosis_name,
        "evidence_summary": evidence_summary,
        "selected_at": datetime.now(timezone.utc).isoformat(),
        "status": "working_diagnosis"
    }
    state.setdefault("current_diagnosis_ids", [])
    if diagnosis_id not in state["current_diagnosis_ids"]:
        state["current_diagnosis_ids"].append(diagnosis_id)
    state.setdefault("diagnoses", {})[diagnosis_id] = diagnosis
    write_patient_state(state, patient_id)
    return diagnosis
