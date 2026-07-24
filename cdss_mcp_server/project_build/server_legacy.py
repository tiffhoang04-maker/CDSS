# 07/24: i am laying this server to rest because it's gotten too overwhelming
import re
from typing import Any

from mcp.server.fastmcp import FastMCP

from neo4j_client import Neo4jClient
from cdss_mcp_server.project_build.state_manager_legacy import (
    read_patient_state,
    read_scenario,
    add_completed_action,
    record_clinical_observation as save_clinical_observation,
    record_patient_diagnosis,
    record_patient_test_result,
    update_stage,
)

mcp = FastMCP("CDSS MCP Server")
neo4j_client = Neo4jClient()

TEST_FIELD_IDS = {
    "ExMCaction:7": "carbon_dioxide",
    "ExMCaction:82": "blood_gases",
    "ExMCaction:83": "blood_pressure",
    "ExMCaction:102": "spo2",
    "ExMCaction:104": "heart_rate",
    "ExMCaction:107": "respiratory_rate",
    "ExMCaction:109": "lung_auscultation",
    "ExMCaction:110": "temperature"
}

ALLOWED_OBSERVATION_STATUSES = {
    "abnormal",
    "known",
    "normal",
    "not_recorded",
    "stale",
    "unavailable",
    "unknown"
}

ALLOWED_OBSERVATION_SOURCES = {
    "clinician",
    "device",
    "scenario",
    "test",
    "user"
}


def _flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings = []
        for nested_value in value.values():
            strings.extend(_flatten_strings(nested_value))
        return strings
    if isinstance(value, list):
        strings = []
        for nested_value in value:
            strings.extend(_flatten_strings(nested_value))
        return strings
    return []


def _get_case_terms(scenario: dict[str, Any]) -> tuple[list[str], list[str]]:
    seed_terms = scenario.get("kg_seed_terms", {})
    symptom_terms = {
        str(term).strip().lower()
        for group in ("symptoms", "conditions", "diseases")
        for term in seed_terms.get(group, [])
        if str(term).strip()
    }

    context_text = " ".join(
        _flatten_strings({
            "title": scenario.get("title"),
            "domain": scenario.get("domain"),
            "setting": scenario.get("setting")
        })
    ).replace("_", " ").lower()
    stop_words = {
        "after", "care", "case", "delayed", "following", "illness",
        "limited", "remote", "setting", "terrestrial", "with"
    }
    context_terms = {
        token
        for token in re.findall(r"[a-z][a-z-]{3,}", context_text)
        if token not in stop_words
    }

    return sorted(symptom_terms), sorted(context_terms)


def _check_resource_availability_internal(
    resource_id: str,
    scenario: dict[str, Any]
) -> dict[str, Any]:
    scenario_resources = scenario.get("starting_context", {}).get(
        "available_resources",
        []
    )
    for resource in scenario_resources:
        if resource.get("resource_id") == resource_id:
            status = str(resource.get("availability", "unknown")).lower()
            return {
                "resource_id": resource_id,
                "resource_name": resource.get("name"),
                "availability": status,
                "is_available": status in {"available", "limited"},
                "availability_source": "scenario",
                "details": resource
            }

    graph_resources = neo4j_client.get_resource(resource_id)
    if not graph_resources:
        return {
            "resource_id": resource_id,
            "availability": "not_found",
            "is_available": False,
            "availability_source": "none",
            "reason": "No matching scenario resource, Action, or MedKit node."
        }

    resource = graph_resources[0]
    node_labels = set(resource.get("node_labels", []))
    if "MedKit" in node_labels:
        inventory_ids = scenario.get("medkit_option_ids", [])
        if inventory_ids:
            is_available = resource_id in inventory_ids
            status = "available" if is_available else "not_in_scenario_inventory"
        else:
            is_available = None
            status = "graph_present_inventory_not_constrained"
    else:
        is_available = None
        status = "graph_defined_availability_not_verified"

    return {
        **resource,
        "availability": status,
        "is_available": is_available,
        "availability_source": (
            "scenario_medkit_inventory"
            if "MedKit" in node_labels and scenario.get("medkit_option_ids")
            else "knowledge_graph_only"
        ),
        "warning": (
            "Presence in the knowledge graph does not by itself prove that "
            "the physical resource is available."
        )
    }


def _get_valid_options_internal() -> dict[str, Any]:
    state = read_patient_state("current_patient")
    scenario = read_scenario(state["scenario_id"])

    current_stage = state["current_stage"]
    completed_action_ids = set(state.get("completed_action_ids", []))
    kg_seed_terms = scenario.get("kg_seed_terms", {})
    action_filter_terms = (
        kg_seed_terms.get("symptoms", [])
        + kg_seed_terms.get("conditions", [])
        + kg_seed_terms.get("diseases", [])
    )

    raw_actions = neo4j_client.get_stage_actions(
        current_stage,
        action_filter_terms,
        scenario.get("medkit_option_ids")
    )

    valid_actions = []
    for action in raw_actions:
        option_id = str(action.get("option_id"))

        if option_id in completed_action_ids:
            continue

        valid_actions.append({
            "option_id": option_id,
            "label": action.get("label"),
            "name": action.get("name"),
            "phrase": action.get("phrase"),
            "route_of_use": action.get("route_of_use"),
            "strength_volume": action.get("strength_volume"),
            "location": action.get("location"),
            "qty_in_pack": action.get("qty_in_pack"),
            "node_labels": action.get("node_labels"),
            "source": "neo4j"
        })

    allowed_stage_transitions = scenario.get("allowed_stage_transitions", {})
    valid_next_stages = allowed_stage_transitions.get(current_stage, [])

    return {
        "patient_id": state.get("patient_id"),
        "scenario_id": state.get("scenario_id"),
        "current_stage": current_stage,
        "valid_actions": valid_actions,
        "valid_next_stages": valid_next_stages,
        "constraints": {
            "llm_must_choose_by_id": True,
            "free_text_choice_allowed": False,
            "invalid_choice_behavior": "reject_and_return_valid_options"
        }
    }


@mcp.tool() # tool 1
# this is a simplified replacement for MedicalInformation / medical_info_cache from charlotte's app
def get_current_patient_state() -> dict[str, Any]:
    """
    Read the current patient state from the local patient record.

    Use this before choosing actions or stages. This tool does not modify state.
    """
    state = read_patient_state("current_patient")
    scenario = read_scenario(state["scenario_id"])

    return {
        "patient_state": state,
        "scenario_summary": {
            "scenario_id": scenario.get("scenario_id"),
            "title": scenario.get("title"),
            "domain": scenario.get("domain"),
            "setting": scenario.get("setting"),
            "public_context": scenario.get("public_context", {})
        }
    }

#initial assessment emergency "checklist" requirements that are used for terrestrial emergency triaging systems

DEFAULT_INITIAL_ASSESSMENT_REQUIREMENTS = [
    # ---------------------------------------------------------
    # Encounter context
    # ---------------------------------------------------------
    {
        "field_id": "chief_complaint",
        "display_name": "Chief complaint",
        "category": "presenting_problem",
        "priority": "critical",
        "acquisition_method": "ask_user",
        "prompt": "What happened, and what is the patient's main medical concern?",
        "blocking": True,
        "repeatable": False
    },
    {
        "field_id": "symptom_onset",
        "display_name": "Symptom onset",
        "category": "presenting_problem",
        "priority": "high",
        "acquisition_method": "ask_user",
        "prompt": "When did the symptoms begin?",
        "blocking": False,
        "repeatable": False
    },

    # ---------------------------------------------------------
    # A: Airway
    # ---------------------------------------------------------
    {
        "field_id": "airway_status",
        "display_name": "Airway status",
        "category": "airway",
        "priority": "critical",
        "acquisition_method": "observe",
        "prompt": (
            "Assess whether the airway is open. Can the patient speak, "
            "and are there signs of obstruction?"
        ),
        "blocking": True,
        "repeatable": True
    },

    # ---------------------------------------------------------
    # B: Breathing
    # ---------------------------------------------------------
    {
        "field_id": "respiratory_rate",
        "display_name": "Respiratory rate",
        "category": "breathing",
        "priority": "critical",
        "acquisition_method": "measure",
        "prompt": "Measure and enter the patient's respiratory rate.",
        "unit": "breaths/min",
        "blocking": True,
        "repeatable": True
    },
    {
        "field_id": "spo2",
        "display_name": "Oxygen saturation",
        "category": "breathing",
        "priority": "critical",
        "acquisition_method": "device_measurement",
        "required_resource": "pulse_oximeter",
        "prompt": "Measure and enter the patient's oxygen saturation.",
        "unit": "%",
        "blocking": True,
        "repeatable": True
    },
    {
        "field_id": "work_of_breathing",
        "display_name": "Work of breathing",
        "category": "breathing",
        "priority": "critical",
        "acquisition_method": "observe",
        "prompt": (
            "Is the patient breathing comfortably, or are there signs "
            "of respiratory distress?"
        ),
        "blocking": True,
        "repeatable": True
    },

    # ---------------------------------------------------------
    # C: Circulation
    # ---------------------------------------------------------
    {
        "field_id": "heart_rate",
        "display_name": "Heart rate",
        "category": "circulation",
        "priority": "critical",
        "acquisition_method": "device_measurement",
        "prompt": "Measure and enter the patient's heart rate.",
        "unit": "beats/min",
        "blocking": True,
        "repeatable": True
    },
    {
        "field_id": "blood_pressure",
        "display_name": "Blood pressure",
        "category": "circulation",
        "priority": "critical",
        "acquisition_method": "device_measurement",
        "required_resource": "blood_pressure_monitor",
        "prompt": "Measure and enter the patient's blood pressure.",
        "unit": "mmHg",
        "blocking": True,
        "repeatable": True
    },
    {
        "field_id": "major_bleeding",
        "display_name": "Major external bleeding",
        "category": "circulation",
        "priority": "critical",
        "acquisition_method": "observe",
        "prompt": "Is there any major external bleeding?",
        "blocking": True,
        "repeatable": True
    },
    {
        "field_id": "perfusion_status",
        "display_name": "Perfusion status",
        "category": "circulation",
        "priority": "high",
        "acquisition_method": "examine",
        "prompt": (
            "Assess skin color, skin temperature, and other signs of "
            "poor circulation."
        ),
        "blocking": False,
        "repeatable": True
    },

    # ---------------------------------------------------------
    # D: Disability / neurologic status
    # ---------------------------------------------------------
    {
        "field_id": "mental_status",
        "display_name": "Mental status",
        "category": "disability",
        "priority": "critical",
        "acquisition_method": "observe",
        "prompt": (
            "Is the patient alert and oriented, confused, responsive "
            "only to voice or pain, or unresponsive?"
        ),
        "blocking": True,
        "repeatable": True
    },
    {
        "field_id": "focal_neurologic_deficit",
        "display_name": "Focal neurologic deficit",
        "category": "disability",
        "priority": "high",
        "acquisition_method": "examine",
        "prompt": (
            "Check for new weakness, facial asymmetry, speech changes, "
            "or unequal movement."
        ),
        "blocking": False,
        "repeatable": True
    },

    # ---------------------------------------------------------
    # E: Exposure and environment
    # ---------------------------------------------------------
    {
        "field_id": "temperature",
        "display_name": "Body temperature",
        "category": "exposure",
        "priority": "high",
        "acquisition_method": "device_measurement",
        "required_resource": "thermometer",
        "prompt": "Measure and enter the patient's temperature.",
        "unit": "degC",
        "blocking": False,
        "repeatable": True
    },
    {
        "field_id": "visible_injury",
        "display_name": "Visible injury",
        "category": "exposure",
        "priority": "high",
        "acquisition_method": "examine",
        "prompt": (
            "Check for visible injury, swelling, wounds, burns, rash, "
            "or deformity."
        ),
        "blocking": False,
        "repeatable": True
    },
    {
        "field_id": "environmental_exposure",
        "display_name": "Environmental exposure",
        "category": "exposure",
        "priority": "high",
        "acquisition_method": "ask_user",
        "prompt": (
            "Was the patient exposed to pressure change, altitude, "
            "temperature extremes, smoke, chemicals, radiation, or trauma?"
        ),
        "blocking": False,
        "repeatable": False
    },

    # ---------------------------------------------------------
    # Essential history
    # ---------------------------------------------------------
    {
        "field_id": "allergies",
        "display_name": "Allergies",
        "category": "medical_history",
        "priority": "high",
        "acquisition_method": "record_or_ask",
        "prompt": "Does the patient have any medication or other allergies?",
        "blocking": True,
        "required_before": "medication_administration",
        "repeatable": False
    },
    {
        "field_id": "current_medications",
        "display_name": "Current medications",
        "category": "medical_history",
        "priority": "high",
        "acquisition_method": "record_or_ask",
        "prompt": "What medications is the patient currently taking?",
        "blocking": False,
        "repeatable": False
    },
    {
        "field_id": "relevant_medical_history",
        "display_name": "Relevant medical history",
        "category": "medical_history",
        "priority": "high",
        "acquisition_method": "record_or_ask",
        "prompt": (
            "Does the patient have any relevant medical conditions, "
            "previous episodes, surgeries, or recent illnesses?"
        ),
        "blocking": False,
        "repeatable": False
    }
]


def _get_merged_clinical_data(
    state: dict[str, Any],
    scenario: dict[str, Any]
) -> dict[str, Any]:
    """Return only observations explicitly recorded in patient state.

    Scenario fixtures may contain private or simulated findings, so values in
    ``starting_context`` must not automatically become known clinical data.
    """
    del scenario
    return dict(state.get("clinical_data", {}))


def _get_information_requirements(
    scenario: dict[str, Any]
) -> list[dict[str, Any]]:
    requirements = list(DEFAULT_INITIAL_ASSESSMENT_REQUIREMENTS)
    requirements.extend(scenario.get("information_requirements", []))
    return list({
        requirement["field_id"]: requirement
        for requirement in requirements
    }.values())


def _is_missing_clinical_value(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    return value.get("status") in {"unknown", "not_recorded", "stale"}


def _assess_information_gaps_internal(
    state: dict[str, Any],
    scenario: dict[str, Any]
) -> dict[str, Any]:
    clinical_data = _get_merged_clinical_data(state, scenario)
    requirements = _get_information_requirements(scenario)
    missing_information = []

    for requirement in requirements:
        field_id = requirement["field_id"]
        if not _is_missing_clinical_value(clinical_data.get(field_id)):
            continue

        missing_information.append({
            "field_id": field_id,
            "display_name": requirement.get("display_name"),
            "category": requirement.get("category"),
            "priority": requirement.get("priority", "routine"),
            "blocking": requirement.get("blocking", False),
            "acquisition_method": requirement.get(
                "acquisition_method",
                "ask_user"
            ),
            "prompt": requirement.get("prompt"),
            "reason": requirement.get("reason")
        })

    priority_order = {"critical": 0, "high": 1, "routine": 2}
    missing_information.sort(
        key=lambda item: priority_order.get(item["priority"], 3)
    )
    blocking_fields = [
        item for item in missing_information if item["blocking"]
    ]

    return {
        "patient_id": state.get("patient_id"),
        "current_stage": state.get("current_stage"),
        "record_status": (
            "blank"
            if not clinical_data
            else "complete"
            if not missing_information
            else "partially_complete"
        ),
        "known_information_fields": sorted(clinical_data),
        "missing_information": missing_information,
        "next_acquisition_requests": missing_information[:3],
        "can_proceed_with_full_assessment": len(blocking_fields) == 0,
        "instructions": {
            "do_not_repeat_known_questions": True,
            "prioritize_immediate_threats": True,
            "request_measurement_when_value_is_missing": True,
            "do_not_assume_missing_values_are_normal": True
        }
    }


def _resolve_test_field_id(test_id: str, label: str = "") -> str:
    if test_id in TEST_FIELD_IDS:
        return TEST_FIELD_IDS[test_id]

    normalized_label = label.lower()
    label_mappings = {
        "blood gas": "blood_gases",
        "blood pressure": "blood_pressure",
        "carbon dioxide": "carbon_dioxide",
        "oxygen saturation": "spo2",
        "respiratory rate": "respiratory_rate",
        "stethoscope": "lung_auscultation",
        "temperature": "temperature",
        "pulse": "heart_rate"
    }
    for phrase, field_id in label_mappings.items():
        if phrase in normalized_label:
            return field_id

    safe_test_id = re.sub(r"[^a-z0-9]+", "_", test_id.lower()).strip("_")
    return f"test_result_{safe_test_id}"


def _get_pending_test_results(
    state: dict[str, Any],
    scenario: dict[str, Any]
) -> list[dict[str, Any]]:
    completed_ids = state.get("completed_action_ids", [])
    completed_labels = state.get("completed_action_labels", [])
    test_results = state.get("test_results", {})
    clinical_data = _get_merged_clinical_data(state, scenario)
    pending_results = []

    for index, test_id in enumerate(completed_ids):
        if test_id in test_results:
            continue
        label = (
            completed_labels[index]
            if index < len(completed_labels)
            else test_id
        )
        field_id = _resolve_test_field_id(test_id, label)
        if not _is_missing_clinical_value(clinical_data.get(field_id)):
            continue
        pending_results.append({
            "test_id": test_id,
            "test_label": label,
            "field_id": field_id,
            "prompt": (
                f"What result was obtained for '{label}'? Include the value, "
                "units when applicable, and whether it was normal, abnormal, "
                "or unavailable."
            ),
            "record_with_tool": "record_test_result"
        })

    return pending_results


def _get_next_clinical_step_internal(
    state: dict[str, Any],
    scenario: dict[str, Any]
) -> dict[str, Any]:
    pending_results = _get_pending_test_results(state, scenario)
    if pending_results:
        return {
            "next_step_type": "request_test_result",
            **pending_results[0],
            "instruction": "Ask the prompt verbatim, wait, then record the answer."
        }

    gap_assessment = _assess_information_gaps_internal(state, scenario)
    blocking_requests = [
        request
        for request in gap_assessment["missing_information"]
        if request["blocking"]
    ]
    if blocking_requests:
        request = blocking_requests[0]
        return {
            "next_step_type": "request_information",
            **request,
            "record_with_tool": "record_clinical_observation",
            "instruction": "Ask the prompt verbatim, wait, then record the answer."
        }

    if (
        state.get("current_stage") == "Diagnosis Stage"
        and not state.get("current_diagnosis_ids")
    ):
        return {
            "next_step_type": "review_differential",
            "tool": "get_differential_diagnoses",
            "instruction": (
                "Retrieve graph candidates, inspect evidence, and then use "
                "record_diagnosis_selection for the selected candidate."
            )
        }

    valid_options = _get_valid_options_internal()
    if valid_options["valid_actions"]:
        return {
            "next_step_type": "choose_action",
            "tool": "get_valid_options",
            "valid_actions": valid_options["valid_actions"],
            "instruction": "Choose only an exact returned option_id."
        }
    if valid_options["valid_next_stages"]:
        return {
            "next_step_type": "transition_stage",
            "tool": "submit_choice",
            "valid_next_stages": valid_options["valid_next_stages"],
            "instruction": "Submit only an exact returned stage name."
        }

    return {
        "next_step_type": "workflow_complete_or_blocked",
        "instruction": "No remaining graph action or stage transition is available."
    }

# new tool added with the intention of prompting users if necessary info is missing
#@mcp.tool() --> makin this internal
def assess_information_gaps() -> dict[str, Any]:
    """
    Identify missing patient information and return structured prompts
    or measurement requests.

    Universal emergency assessment fields are checked first, followed
    by scenario-specific and differential-specific requirements.
    """
    state = read_patient_state("current_patient")
    scenario = read_scenario(state["scenario_id"])
    return _assess_information_gaps_internal(state, scenario)


@mcp.tool()
def get_next_clinical_step() -> dict[str, Any]:
    """
    Return exactly one next workflow directive. For request_test_result or
    request_information, ask the returned prompt verbatim, wait for the user,
    and then call the named recording tool.
    """
    state = read_patient_state("current_patient")
    scenario = read_scenario(state["scenario_id"])
    return {
        "patient_id": state.get("patient_id"),
        "scenario_id": state.get("scenario_id"),
        "current_stage": state.get("current_stage"),
        **_get_next_clinical_step_internal(state, scenario)
    }


@mcp.tool()
def record_clinical_observation(
    field_id: str,
    value: str,
    unit: str = "",
    status: str = "known",
    source: str = "user"
) -> dict[str, Any]:
    """
    Persist one answer or clinical observation requested by the workflow,
    then immediately reassess gaps and return the next clinical step.
    """
    state = read_patient_state("current_patient")
    scenario = read_scenario(state["scenario_id"])
    allowed_field_ids = {
        requirement["field_id"]
        for requirement in _get_information_requirements(scenario)
    }
    if field_id not in allowed_field_ids:
        return {
            "accepted": False,
            "field_id": field_id,
            "reason": "field_id is not a configured information requirement.",
            "allowed_field_ids": sorted(allowed_field_ids)
        }
    if status not in ALLOWED_OBSERVATION_STATUSES:
        return {
            "accepted": False,
            "field_id": field_id,
            "reason": "Unsupported status.",
            "allowed_statuses": sorted(ALLOWED_OBSERVATION_STATUSES)
        }
    if source not in ALLOWED_OBSERVATION_SOURCES:
        return {
            "accepted": False,
            "field_id": field_id,
            "reason": "Unsupported source.",
            "allowed_sources": sorted(ALLOWED_OBSERVATION_SOURCES)
        }

    observation = save_clinical_observation(
        field_id=field_id,
        value=value,
        unit=unit,
        status=status,
        source=source,
        patient_id="current_patient"
    )
    return {
        "accepted": True,
        "field_id": field_id,
        "observation": observation,
        "reassessment": reassess_patient()
    }


@mcp.tool()
def record_test_result(
    test_id: str,
    result: str,
    field_id: str = "",
    unit: str = "",
    status: str = "known",
    source: str = "user"
) -> dict[str, Any]:
    """
    Persist the result of a completed action/test, map it into clinical_data,
    and immediately return a reassessment and the next workflow directive.
    """
    state = read_patient_state("current_patient")
    if test_id not in state.get("completed_action_ids", []):
        return {
            "accepted": False,
            "test_id": test_id,
            "reason": "The test_id is not in completed_action_ids.",
            "completed_action_ids": state.get("completed_action_ids", [])
        }
    if status not in ALLOWED_OBSERVATION_STATUSES:
        return {
            "accepted": False,
            "test_id": test_id,
            "reason": "Unsupported status.",
            "allowed_statuses": sorted(ALLOWED_OBSERVATION_STATUSES)
        }
    if source not in ALLOWED_OBSERVATION_SOURCES:
        return {
            "accepted": False,
            "test_id": test_id,
            "reason": "Unsupported source.",
            "allowed_sources": sorted(ALLOWED_OBSERVATION_SOURCES)
        }

    completed_ids = state.get("completed_action_ids", [])
    completed_labels = state.get("completed_action_labels", [])
    test_index = completed_ids.index(test_id)
    test_label = (
        completed_labels[test_index]
        if test_index < len(completed_labels)
        else test_id
    )
    resolved_field_id = field_id or _resolve_test_field_id(test_id, test_label)
    test_result = record_patient_test_result(
        test_id=test_id,
        result=result,
        field_id=resolved_field_id,
        unit=unit,
        status=status,
        source=source,
        patient_id="current_patient"
    )

    return {
        "accepted": True,
        "test_result": test_result,
        "reassessment": reassess_patient()
    }


@mcp.tool()
def record_diagnosis_selection(
    diagnosis_id: str,
    evidence_summary: str = ""
) -> dict[str, Any]:
    """
    Persist one exact Neo4j Condition or Disease ID as the working diagnosis,
    then reassess the workflow. Use an ID returned by the differential tool.
    """
    state = read_patient_state("current_patient")
    scenario = read_scenario(state["scenario_id"])
    symptom_terms, _ = _get_case_terms(scenario)
    evidence_rows = neo4j_client.get_diagnosis_evidence(
        diagnosis_id,
        symptom_terms
    )
    if not evidence_rows:
        return {
            "accepted": False,
            "diagnosis_id": diagnosis_id,
            "reason": "No Condition or Disease node has this exact ID."
        }

    diagnosis = record_patient_diagnosis(
        diagnosis_id=diagnosis_id,
        diagnosis_name=evidence_rows[0].get("diagnosis_name"),
        evidence_summary=evidence_summary,
        patient_id="current_patient"
    )
    return {
        "accepted": True,
        "diagnosis": diagnosis,
        "reassessment": reassess_patient()
    }


#@mcp.tool() --> making this internal
def reassess_patient() -> dict[str, Any]:
    """
    Recompute pending test results, missing information, and the single next
    workflow directive after any recorded answer, result, or diagnosis.
    """
    state = read_patient_state("current_patient")
    scenario = read_scenario(state["scenario_id"])
    return {
        "patient_id": state.get("patient_id"),
        "scenario_id": state.get("scenario_id"),
        "current_stage": state.get("current_stage"),
        "pending_test_results": _get_pending_test_results(state, scenario),
        "information_gap_assessment": _assess_information_gaps_internal(
            state,
            scenario
        ),
        "next_clinical_step": _get_next_clinical_step_internal(
            state,
            scenario
        )
    }


#differentail candidates have graph overlap and are considered potential candidates, not confirmed diagnoses
@mcp.tool()
def get_differential_diagnoses(limit: int = 10) -> dict[str, Any]:
    """
    Return knowledge-graph diagnosis candidates ranked by explicit overlap
    with the current case. Results are candidates, not confirmed diagnoses.
    """
    state = read_patient_state("current_patient")
    scenario = read_scenario(state["scenario_id"])
    symptom_terms, context_terms = _get_case_terms(scenario)
    safe_limit = max(1, min(limit, 50))

    candidates = neo4j_client.get_differential_diagnoses(
        symptom_terms=symptom_terms,
        context_terms=context_terms,
        limit=safe_limit
    )

    return {
        "patient_id": state.get("patient_id"),
        "scenario_id": state.get("scenario_id"),
        "current_stage": state.get("current_stage"),
        "candidates": candidates,
        "candidate_count": len(candidates),
        "provenance": {
            "source": "neo4j",
            "symptom_terms_used": symptom_terms,
            "context_terms_used": context_terms,
            "ranking": "Graph overlap score, not clinical probability."
        },
        "warning": (
            "Do not treat candidates as confirmed diagnoses. Review the "
            "evidence for each candidate and obtain missing clinical data."
        )
    }


@mcp.tool()
def get_diagnosis_evidence(diagnosis_id: str) -> dict[str, Any]:
    """
    Return graph evidence for one exact diagnosis ID from the differential
    tool, including which graph symptoms match current case seed terms.
    """
    state = read_patient_state("current_patient")
    scenario = read_scenario(state["scenario_id"])
    symptom_terms, context_terms = _get_case_terms(scenario)
    rows = neo4j_client.get_diagnosis_evidence(
        diagnosis_id=diagnosis_id,
        symptom_terms=symptom_terms
    )

    if not rows:
        return {
            "found": False,
            "diagnosis_id": diagnosis_id,
            "reason": "No Condition or Disease node has this exact ID."
        }

    evidence = rows[0]
    graph_symptoms = evidence.get("graph_symptoms", [])
    supporting_symptoms = [
        symptom for symptom in graph_symptoms
        if symptom.get("matches_patient_terms")
    ]
    diagnosis_name = str(evidence.get("diagnosis_name", "")).lower()
    matched_context_terms = [
        term for term in context_terms if term in diagnosis_name
    ]

    if supporting_symptoms:
        evidence_status = "graph_symptom_overlap"
    elif matched_context_terms:
        evidence_status = "context_name_overlap_only"
    else:
        evidence_status = "no_current_case_overlap_found"

    return {
        "found": True,
        **evidence,
        "supporting_graph_symptoms": supporting_symptoms,
        "matched_context_terms": matched_context_terms,
        "evidence_status": evidence_status,
        "provenance": "neo4j plus current public scenario terms",
        "warning": "Graph association is not diagnostic confirmation."
    }


@mcp.tool()
def get_recommended_tests(
    diagnosis_id: str,
    limit: int = 20
) -> dict[str, Any]:
    """
    Return Neo4j Action nodes linked to an exact diagnosis ID by a diagnostic
    relationship. Resource availability is reported separately for each test.
    """
    state = read_patient_state("current_patient")
    scenario = read_scenario(state["scenario_id"])
    safe_limit = max(1, min(limit, 50))
    tests = neo4j_client.get_recommended_tests(diagnosis_id, safe_limit)

    for test in tests:
        availability = _check_resource_availability_internal(
            test["test_id"],
            scenario
        )
        test["resource_availability"] = {
            "availability": availability.get("availability"),
            "is_available": availability.get("is_available"),
            "availability_source": availability.get("availability_source")
        }

    return {
        "patient_id": state.get("patient_id"),
        "diagnosis_id": diagnosis_id,
        "recommended_tests": tests,
        "test_count": len(tests),
        "provenance": "Neo4j DIAGNOSES_AdC relationships",
        "warning": (
            "A graph recommendation and a graph-defined Action do not prove "
            "that a physical test resource is currently available."
        )
    }


@mcp.tool()
def check_resource_availability(resource_id: str) -> dict[str, Any]:
    """
    Check one exact scenario, MedKit, or Action resource ID. Distinguishes
    physical scenario availability from mere knowledge-graph presence.
    """
    state = read_patient_state("current_patient")
    scenario = read_scenario(state["scenario_id"])
    return {
        "patient_id": state.get("patient_id"),
        "scenario_id": state.get("scenario_id"),
        **_check_resource_availability_internal(resource_id, scenario)
    }


@mcp.tool()
def explain_recommendation(
    recommendation_id: str,
    diagnosis_id: str
) -> dict[str, Any]:
    """
    Explain one exact test, action, or MedKit recommendation using only
    whitelisted Neo4j relationship paths and current resource availability.
    """
    state = read_patient_state("current_patient")
    scenario = read_scenario(state["scenario_id"])
    paths = neo4j_client.explain_recommendation(
        diagnosis_id=diagnosis_id,
        recommendation_id=recommendation_id
    )
    availability = _check_resource_availability_internal(
        recommendation_id,
        scenario
    )
    relationship_meanings = {
        "DIAGNOSES_AdC": "The graph links the Action as diagnostic for the Condition.",
        "TREATS_MKtC": "The graph links the MedKit resource as treating the Condition.",
        "ASSISTSTREATMENT_MKaC": "The graph links the MedKit resource as assisting treatment.",
        "ASSISTSTREATMENT_AaC": "The graph links the Action as assisting treatment.",
        "MAPSTO_CmD": "The graph maps the Condition to the Disease.",
        "INCLUDES_MKiMK": "The graph places the resource inside a MedKit category."
    }
    relationships = sorted({
        relationship
        for path in paths
        for relationship in path.get("relationships", [])
    })

    return {
        "diagnosis_id": diagnosis_id,
        "recommendation_id": recommendation_id,
        "supported_by_graph": bool(paths),
        "graph_paths": paths,
        "relationship_explanations": [
            relationship_meanings[relationship]
            for relationship in relationships
            if relationship in relationship_meanings
        ],
        "resource_availability": availability,
        "provenance": "Neo4j relationship paths plus public scenario inventory",
        "warning": (
            "This explains graph provenance; it does not independently "
            "establish clinical appropriateness."
        )
    }

#@mcp.tool() # tool 2 --> MAKING THIS INTERNAL BC it forces model to keep picking an action as opposed to just progressing to patient reassessment
# MCP version of charlotte's action_list_dict + return_action_lists
def get_valid_options() -> dict[str, Any]:
    """
    Return the valid action IDs and valid next stage IDs for the current patient stage.

    The LLM should choose only from these returned IDs/stage names.
    """
    return _get_valid_options_internal()


@mcp.tool() # tool 3
# new validatin layer that Charlotte's app didn't have
# this layer is CRUCIAL because it ensure our LLM receives explicit IDs 
# the server must reject anything outside the valid list
def submit_choice(
    choice_type: str,
    choice_id: str
) -> dict[str, Any]:
    """
    Validate and apply a model-selected option.

    choice_type must be:
    - "action" for an action option_id
    - "stage" for a stage transition

    Invalid choices are rejected and the valid options are returned.
    """
    valid_options = _get_valid_options_internal()

    if choice_type == "action":
        allowed_actions = {
            action["option_id"]: action
            for action in valid_options["valid_actions"]
        }

        if choice_id not in allowed_actions:
            return {
                "accepted": False,
                "reason": "Action choice_id is not in the valid action list.",
                "submitted_choice": {
                    "choice_type": choice_type,
                    "choice_id": choice_id
                },
                "valid_options": valid_options
            }

        chosen_action = allowed_actions[choice_id]
        updated_state = add_completed_action(
            choice_id=choice_id,
            choice_label=chosen_action.get("label"),
            patient_id="current_patient"
        )

        return {
            "accepted": True,
            "choice_type": "action",
            "choice_id": choice_id,
            "choice_label": chosen_action.get("label"),
            "updated_patient_state": updated_state,
            "next_valid_options": _get_valid_options_internal()
        }

    if choice_type == "stage":
        allowed_stages = set(valid_options["valid_next_stages"])

        if choice_id not in allowed_stages:
            return {
                "accepted": False,
                "reason": "Stage choice_id is not an allowed next stage.",
                "submitted_choice": {
                    "choice_type": choice_type,
                    "choice_id": choice_id
                },
                "valid_options": valid_options
            }

        updated_state = update_stage(
            new_stage=choice_id,
            patient_id="current_patient"
        )

        return {
            "accepted": True,
            "choice_type": "stage",
            "choice_id": choice_id,
            "updated_patient_state": updated_state,
            "next_valid_options": _get_valid_options_internal()
        }

    return {
        "accepted": False,
        "reason": "choice_type must be either 'action' or 'stage'.",
        "submitted_choice": {
            "choice_type": choice_type,
            "choice_id": choice_id
        },
        "valid_options": valid_options
    }


#@mcp.tool() # tool 4 which i've made internal
#simplified read-only vers of get_kg_context.py 
def get_kg_context_for_patient(
    limit: int = 50
) -> dict[str, Any]:
    """
    Retrieve KG context relevant to the current patient's scenario seed terms.

    This is read-only. It does not choose actions or update state.
    """
    state = read_patient_state("current_patient")
    scenario = read_scenario(state["scenario_id"])

    seed_terms = scenario.get("kg_seed_terms", {})

    symptoms = seed_terms.get("symptoms", [])
    conditions = seed_terms.get("conditions", [])
    diseases = seed_terms.get("diseases", [])

    kg_context = neo4j_client.get_context_by_seed_terms(
        symptoms=symptoms,
        conditions=conditions,
        diseases=diseases,
        limit=limit
    )

    return {
        "patient_id": state.get("patient_id"),
        "scenario_id": state.get("scenario_id"),
        "current_stage": state.get("current_stage"),
        "scenario_context_snippets": scenario.get("clinical_context_snippets", []),
        "kg_seed_terms": seed_terms,
        "kg_context": kg_context
    }


if __name__ == "__main__":
    print("Starting CDSS MCP Server...", flush = True)
    mcp.run(transport="stdio")
