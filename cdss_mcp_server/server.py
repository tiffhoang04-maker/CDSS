# here's the actiual MCP server with four tools (detailed below)
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


def _get_valid_options_internal(patient_id: str = "current_patient") -> dict[str, Any]:
    state = read_patient_state(patient_id)
    scenario = read_scenario(state["scenario_id"])

    current_stage = state["current_stage"]
    completed_action_ids = set(state.get("completed_action_ids", []))
    kg_seed_terms = scenario.get("kg_seed_terms", {})
    action_filter_terms = (
        kg_seed_terms.get("symptoms", [])
        + kg_seed_terms.get("conditions", [])
        + kg_seed_terms.get("diseases", [])
    )

    raw_actions = neo4j_client.get_stage_actions(current_stage, action_filter_terms)

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
def get_current_patient_state(patient_id: str = "current_patient") -> dict[str, Any]:
    """
    Read the current patient state from the local patient record.

    Use this before choosing actions or stages. This tool does not modify state.
    """
    state = read_patient_state(patient_id)
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


@mcp.tool() # tool 2
# MCP version of charlotte's action_list_dict + return_action_lists
def get_valid_options(patient_id: str = "current_patient") -> dict[str, Any]:
    """
    Return the valid action IDs and valid next stage IDs for the current patient stage.

    The LLM should choose only from these returned IDs/stage names.
    """
    return _get_valid_options_internal(patient_id)


@mcp.tool() # tool 3
# new validatin layer that Charlotte's app didn't have
# this layer is CRUCIAL because it ensure our LLM receives explicit IDs 
# the server must reject anything outside the valid list
def submit_choice(
    choice_type: str,
    choice_id: str,
    patient_id: str = "current_patient"
) -> dict[str, Any]:
    """
    Validate and apply a model-selected option.

    choice_type must be:
    - "action" for an action option_id
    - "stage" for a stage transition

    Invalid choices are rejected and the valid options are returned.
    """
    valid_options = _get_valid_options_internal(patient_id)

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
            patient_id=patient_id
        )

        return {
            "accepted": True,
            "choice_type": "action",
            "choice_id": choice_id,
            "choice_label": chosen_action.get("label"),
            "updated_patient_state": updated_state,
            "next_valid_options": _get_valid_options_internal(patient_id)
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
            patient_id=patient_id
        )

        return {
            "accepted": True,
            "choice_type": "stage",
            "choice_id": choice_id,
            "updated_patient_state": updated_state,
            "next_valid_options": _get_valid_options_internal(patient_id)
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
    patient_id: str = "current_patient",
    limit: int = 50
) -> dict[str, Any]:
    """
    Retrieve KG context relevant to the current patient's scenario seed terms.

    This is read-only. It does not choose actions or update state.
    """
    state = read_patient_state(patient_id)
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
    mcp.run()
