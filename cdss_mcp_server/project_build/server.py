from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from case_repository import (
    CaseRepositoryError,
    read_persona,
    read_public_scenario,
    read_simulation_scenario
)
from cdss_mcp_server.project_build.state_manager_legacy import (
    StateManagerError,
    initialize_patient_state,
    mark_trigger_completed,
    read_patient_state,
    record_observation
)


mcp = FastMCP("CDSS MCP Server")


def _public_persona_view(persona: dict[str, Any]) -> dict[str, Any]:
    """Return only persona fields that are safe for the model to see."""
    return {
        "persona_id": persona.get("persona_id"),
        "name": persona.get("name"),
        "public_profile": persona.get("public_profile", {})
    }


@mcp.tool()
def start_case(scenario_id: str) -> dict[str, Any]:
    """
    Initialize one simulation case and return only model-visible case data.
    """
    try:
        scenario = read_public_scenario(scenario_id)
        persona_id = scenario["persona_id"]
        persona = read_persona(persona_id)

        state = initialize_patient_state(
            scenario_id=scenario_id,
            persona_id=persona_id
        )

        return {
            "started": True,
            "public_scenario": scenario,
            "persona": _public_persona_view(persona),
            "patient_state": state
        }

    except (CaseRepositoryError, StateManagerError, KeyError) as error:
        return {
            "started": False,
            "reason": str(error)
        }


@mcp.tool()
def get_patient_state() -> dict[str, Any]:
    """
    Return the current model-visible patient state and public case context.
    """
    try:
        state = read_patient_state()
        scenario = read_public_scenario(state["scenario_id"])
        persona = read_persona(state["persona_id"])

        return {
            "patient_state": state,
            "public_scenario": scenario,
            "persona": _public_persona_view(persona)
        }

    except (CaseRepositoryError, StateManagerError, KeyError) as error:
        return {
            "found": False,
            "reason": str(error)
        }


@mcp.tool()
def perform_assessment(trigger_id: str) -> dict[str, Any]:
    """
    Perform one supported assessment, question, examination, or measurement.

    The trigger_id must correspond to a reveal configured in the hidden
    simulation fixture. The entire simulation fixture is never returned.
    """
    try:
        state = read_patient_state()
        simulation = read_simulation_scenario(state["scenario_id"])
        reveals = simulation.get("reveals", {})

        if trigger_id not in reveals:
            return {
                "accepted": False,
                "trigger_id": trigger_id,
                "reason": "Unsupported assessment trigger."
            }

        if trigger_id in state.get("completed_triggers", []):
            field_id = reveals[trigger_id]["field_id"]
            return {
                "accepted": False,
                "trigger_id": trigger_id,
                "reason": "Assessment already completed.",
                "existing_observation": state.get(
                    "clinical_data",
                    {}
                ).get(field_id)
            }

        reveal = reveals[trigger_id]

        updated_state = record_observation(
            field_id=reveal["field_id"],
            value=reveal.get("value"),
            unit=reveal.get("unit", ""),
            status=reveal.get("status", "known"),
            source=reveal.get("source", "simulation")
        )

        updated_state = mark_trigger_completed(trigger_id)

        return {
            "accepted": True,
            "trigger_id": trigger_id,
            "observation": updated_state["clinical_data"][
                reveal["field_id"]
            ],
            "field_id": reveal["field_id"],
            "patient_state": updated_state
        }

    except (CaseRepositoryError, StateManagerError, KeyError) as error:
        return {
            "accepted": False,
            "trigger_id": trigger_id,
            "reason": str(error)
        }


@mcp.tool()
def record_user_observation(
    field_id: str,
    value: str,
    unit: str = "",
    status: str = "known"
) -> dict[str, Any]:
    """
    Record an observation supplied directly by the clinician or user.
    """
    allowed_statuses = {
        "known",
        "normal",
        "abnormal",
        "unavailable",
        "unable_to_assess"
    }

    if status not in allowed_statuses:
        return {
            "accepted": False,
            "reason": "Unsupported observation status.",
            "allowed_statuses": sorted(allowed_statuses)
        }

    try:
        updated_state = record_observation(
            field_id=field_id,
            value=value,
            unit=unit,
            status=status,
            source="user"
        )

        return {
            "accepted": True,
            "field_id": field_id,
            "patient_state": updated_state
        }

    except StateManagerError as error:
        return {
            "accepted": False,
            "field_id": field_id,
            "reason": str(error)
        }


if __name__ == "__main__":
    print("Starting CDSS MCP Server...", flush=True)
    mcp.run(transport="stdio")