# here's the actiual MCP server with four tools (detailed below)

# edit 7/14: the goal is to
# Automatically retrieve everything already available, explicitly identify what is missing, and ask the clinician only for information that is both obtainable and decision-relevant.

from typing import Any

from mcp.server.fastmcp import FastMCP

from neo4j_client import Neo4jClient
from state_manager import (
    read_patient_state,
    read_scenario,
    add_completed_action,
    update_stage,
)


mcp = FastMCP("CDSS MCP Server")
neo4j_client = Neo4jClient()


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
            "starting_context": scenario.get("starting_context")
        }
    }

# new tool added with the intention of prompting users if necessary info is mjissing
@mcp.tool()
def assess_information_gaps() -> dict[str, Any]:
    """
    Identify missing patient information and return structured prompts
    or measurement requests.

    Universal emergency assessment fields are checked first, followed
    by scenario-specific and differential-specific requirements.
    """
    state = read_patient_state("current_patient")
    scenario = read_scenario(state["scenario_id"])

    clinical_data = state.get("clinical_data", {})

    requirements = list(DEFAULT_INITIAL_ASSESSMENT_REQUIREMENTS)
    requirements.extend(
        scenario.get("information_requirements", [])
    )

    requirements_by_id = {
        requirement["field_id"]: requirement
        for requirement in requirements
    }

    missing_information = []

    for field_id, requirement in requirements_by_id.items():
        current_value = clinical_data.get(field_id)

        missing = (
            current_value is None
            or current_value.get("status") in {
                "unknown",
                "not_recorded",
                "stale"
            }
        )

        if not missing:
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

    priority_order = {
        "critical": 0,
        "high": 1,
        "routine": 2
    }

    missing_information.sort(
        key=lambda item: priority_order.get(
            item["priority"],
            3
        )
    )

    blocking_fields = [
        item for item in missing_information
        if item["blocking"]
    ]

    return {
        "patient_id": state.get("patient_id"),
        "current_stage": state.get("current_stage"),
        "record_status": (
            "blank"
            if not clinical_data
            else "partially_complete"
        ),
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

@mcp.tool() # tool 2
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


@mcp.tool() # tool 4
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
