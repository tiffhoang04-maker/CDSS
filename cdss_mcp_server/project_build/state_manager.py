from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state" / "current_patient.json"


class StateManagerError(Exception):
    """Raised when patient state cannot be read or written."""


# Load and validate the current patient's saved state from the JSON file.
def read_patient_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        raise StateManagerError(
            f"Patient state file does not exist: {STATE_FILE}"
        )

    try:
        with STATE_FILE.open("r", encoding="utf-8") as file:
            state = json.load(file)
    except json.JSONDecodeError as error:
        raise StateManagerError(
            f"Invalid patient-state JSON: {error}"
        ) from error

    if not isinstance(state, dict):
        raise StateManagerError(
            "Patient state must be a JSON object."
        )

    return state


# Save the complete patient state safely by replacing the file atomically.
def write_patient_state(state: dict[str, Any]) -> dict[str, Any]:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    temporary_file = STATE_FILE.with_suffix(".tmp")

    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(state, file, indent=2)
        file.write("\n")

    temporary_file.replace(STATE_FILE)
    return state


# Create a fresh active patient state for the selected scenario and persona.
def initialize_patient_state(
    scenario_id: str,
    persona_id: str
) -> dict[str, Any]:
    state = {
        "patient_id": "current_patient",
        "scenario_id": scenario_id,
        "persona_id": persona_id,
        "status": None, #active or inactive
        "current_stage": None, #initial_assessment, diagnosis, treatment, follow_up
        "clinical_data": {},
        "completed_triggers": [],
        "working_differential": [],
        "working_diagnosis": None
    }

    return write_patient_state(state)


# Add or update one clinical observation in the current patient state.
def record_observation(
    field_id: str,
    value: Any,
    unit: str = "",
    status: str = "known",
    source: str = "simulation"
) -> dict[str, Any]:
    state = read_patient_state()

    state.setdefault("clinical_data", {})[field_id] = {
        "value": value,
        "unit": unit,
        "status": status,
        "source": source
    }

    return write_patient_state(state)

# according to GPT: a trigger ID is a stable internal name for an action that reveals a hidden finding 
# it corresponds to the "reveals" field in the simulation.json
# examples include ask_ascent_history, measure_spo2, measure_heart_rate, etc.
# anyway, once the assessment is done, the trigger id will be added to the completed_triggers list which will present the same assessment from being treated as new every time

# Record that a reveal trigger has been completed without adding it twice.
def mark_trigger_completed(trigger_id: str) -> dict[str, Any]:
    state = read_patient_state()
    completed = state.setdefault("completed_triggers", [])

    if trigger_id not in completed:
        completed.append(trigger_id)

    return write_patient_state(state)
