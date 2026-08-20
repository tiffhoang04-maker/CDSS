from __future__ import annotations

import inspect
import json
import logging
import os
import time
from datetime import datetime, timezone
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from case_repo import (
    CaseRepositoryError, # dis the class
    read_persona, # these are functions of da class
    read_public_scenario,
    read_simulation_scenario
)
from state_manager import (
    StateManagerError,
    initialize_patient_state,
    mark_trigger_completed,
    read_patient_state,
    record_guidance_result,
    record_observation,
    update_current_stage,
)


LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "mcp_server.log"
LOG_PAYLOADS = os.getenv(
    "MCP_LOG_PAYLOADS",
    "false",
).strip().lower() in {"1", "true", "yes", "on"}

LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("cdss_mcp_server")
logger.setLevel(
    getattr(
        logging,
        os.getenv("MCP_LOG_LEVEL", "INFO").upper(),
        logging.INFO,
    )
)
logger.propagate = False

if not any(
    isinstance(handler, RotatingFileHandler)
    and Path(handler.baseFilename) == LOG_FILE
    for handler in logger.handlers
):
    file_handler = RotatingFileHandler(
        LOG_FILE,
        mode="w",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(file_handler)


def _log_event(event: str, **details: Any) -> None:
    """Write one JSON event to the file logger, never to MCP stdout."""
    logger.info(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event,
                **details,
            },
            default=str,
            sort_keys=True,
        )
    )


def _safe_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Avoid persisting observation text unless payload logging is enabled."""
    if LOG_PAYLOADS:
        return inputs

    safe = dict(inputs)
    if "value" in safe:
        safe["value"] = (
            f"<omitted; {len(str(safe['value']))} characters>"
        )
    return safe


def _result_summary(result: Any) -> dict[str, Any]:
    """Extract useful trace metadata without copying entire tool payloads."""
    if not isinstance(result, dict):
        return {"result_type": type(result).__name__}

    summary_keys = {
        "accepted",
        "candidate_id",
        "candidate_type",
        "diagnosis_id",
        "field_id",
        "found",
        "option_count",
        "query",
        "reason",
        "started",
        "status",
        "success",
        "task",
        "trigger_id",
    }
    summary = {
        key: result[key]
        for key in summary_keys
        if key in result
    }

    patient_state = result.get("patient_state")
    if isinstance(patient_state, dict):
        summary["patient_state"] = {
            "scenario_id": patient_state.get("scenario_id"),
            "current_stage": patient_state.get("current_stage"),
            "clinical_data_fields": sorted(
                patient_state.get("clinical_data", {})
            ),
            "completed_triggers": patient_state.get(
                "completed_triggers",
                [],
            ),
            "differential_count": len(
                patient_state.get("working_differential", [])
            ),
        }

    candidates = result.get("candidates")
    if isinstance(candidates, list):
        summary["candidates"] = [
            {
                "id": (
                    item.get("candidate_id")
                    or item.get("diagnosis_id")
                ),
                "name": (
                    item.get("candidate_name")
                    or item.get("diagnosis_name")
                ),
                "type": item.get("candidate_type"),
            }
            for item in candidates
            if isinstance(item, dict)
        ]

    options = result.get("options")
    if isinstance(options, list):
        summary["options"] = [
            {
                "medkit_id": item.get("medkit_id"),
                "name": item.get("name"),
            }
            for item in options
            if isinstance(item, dict)
        ]

    return summary


def _logged_tool(function):
    """Log synchronous MCP tool inputs, results, duration, and exceptions."""
    signature = inspect.signature(function)

    @wraps(function)
    def wrapper(*args, **kwargs):
        bound = signature.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        inputs = _safe_inputs(dict(bound.arguments))
        started_at = time.perf_counter()

        _log_event(
            "tool_start",
            tool=function.__name__,
            inputs=inputs,
        )

        try:
            result = function(*args, **kwargs)
        except Exception as error:
            _log_event(
                "tool_exception",
                tool=function.__name__,
                duration_ms=round(
                    (time.perf_counter() - started_at) * 1000,
                    2,
                ),
                error_type=type(error).__name__,
                error=str(error),
            )
            raise

        event = {
            "tool": function.__name__,
            "duration_ms": round(
                (time.perf_counter() - started_at) * 1000,
                2,
            ),
            "summary": _result_summary(result),
        }
        if LOG_PAYLOADS:
            event["result"] = result
        _log_event("tool_end", **event)
        return result

    return wrapper


mcp = FastMCP("CDSS MCP Server")

_log_event(
    "server_module_loaded",
    server="CDSS MCP Server",
    log_file=str(LOG_FILE),
    payload_logging=LOG_PAYLOADS,
)


def _public_persona_view(persona: dict[str, Any]) -> dict[str, Any]:
    """Return only persona fields that are safe for the model to see."""
    return {
        "persona_id": persona.get("persona_id"),
        "name": persona.get("name"),
        "public_profile": persona.get("public_profile", {})
    }


@mcp.tool()
@_logged_tool
def start_case(scenario_id: str) -> dict[str, Any]:
    """
    Initialize one simulation case from the scenario id and return only model-visible case data.
    """
    try:
        scenario = read_public_scenario(scenario_id)
        persona_id = scenario["persona_id"]
        persona = read_persona(persona_id)

        initial_stage = scenario.get(
            "initial_stage",
            "initial_assessment",
        )

# each successful call to start_case will create a new patient state for the selected scenario and persona, overwriting any existing patient state
        state = initialize_patient_state(
            scenario_id=scenario_id,
            persona_id=persona_id,
            initial_stage = initial_stage,
        )

        return {
            "started": True,
            "public_scenario": scenario,
            "persona": _public_persona_view(persona),
            "patient_state": state,
            "workflow": {
                "current_stage": initial_stage,
                "instruction": (
                    "Begin by collecting relevant assessment findings."
                ),
            },
        }

    except (CaseRepositoryError, StateManagerError, KeyError) as error:
        return {
            "started": False,
            "reason": str(error)
        }


@mcp.tool()
@_logged_tool
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
    
# helper func

def _workflow_status(
    state: dict[str, Any],
    scenario: dict[str, Any],
) -> dict[str, Any]:
    """Summarize workflow progress and recommend the next step."""

    current_stage = state.get(
        "current_stage",
        "initial_assessment",
    )

    completed = set(
        state.get("completed_triggers", [])
    )

    remaining_assessments = [
        assessment
        for assessment in scenario.get(
            "available_assessments",
            [],
        )
        if assessment.get("trigger_id") not in completed
    ]

    working_differential = state.get(
        "working_differential",
        [],
    )

    if current_stage == "initial_assessment":
        if state.get("clinical_data"):
            recommended_next_step = (
                "Use get_clinical_guidance to generate a "
                "differential from the recorded findings."
            )
        else:
            recommended_next_step = (
                "Perform a relevant available assessment."
            )

    elif current_stage == "differential_diagnosis":
        if working_differential:
            recommended_next_step = (
                "Review the differential and collect any "
                "additional distinguishing findings."
            )
        else:
            recommended_next_step = (
                "Formulate a provisional differential and "
                "collect additional findings."
            )

    else:
        recommended_next_step = (
            "Review the patient state and determine the next "
            "appropriate clinical action."
        )

    return {
        "current_stage": current_stage,
        "stage_history": state.get("stage_history", []),
        "completed_assessments": sorted(completed),
        "remaining_assessments": remaining_assessments,
        "working_differential": working_differential,
        "recommended_next_step": recommended_next_step,
    }

@mcp.tool()
@_logged_tool
def get_workflow_status() -> dict[str, Any]:
    """
    Return the current workflow state and recommend the next useful step.

    The user does not need to manually advance workflow stages.
    """
    try:
        state = read_patient_state()
        scenario = read_public_scenario(
            state["scenario_id"]
        )

        return {
            "success": True,
            "workflow": _workflow_status(
                state,
                scenario,
            ),
        }

    except (
        CaseRepositoryError,
        StateManagerError,
        KeyError,
    ) as error:
        return {
            "success": False,
            "reason": str(error),
        }


@mcp.tool()
# trigger_id corresponds to a "reveal" field in the simulation.json
# ex: perform_assessment("measure_spo2") will look up the hidden result associated with the measure_spo2 assessment
#  and then add the SPO2 value in the visible patient state
@_logged_tool
def perform_assessment(trigger_id: str) -> dict[str, Any]:
    """
    Perform one assessment from public_scenario.available_assessments.

    Use the exact trigger_id returned in available_assessments.
    Never invent or modify a trigger ID.

    for example, perform_assessment("measure_spo2") will look up the hidden result associated with the measure_spo2 assessment
    and then add the SPO2 value in the visible patient state in this format:
    "{"accepted": True,
            "trigger_id": spo2,
            "observation": {
            },
            "field_id": reveal["field_id"],
            "patient_state": updated_state
    }"
    """
    try:
        state = read_patient_state()
        simulation = read_simulation_scenario(state["scenario_id"])
        reveals = simulation.get("reveals", {})

        if trigger_id not in reveals:
            public_scenario = read_public_scenario(state["scenario_id"])
            return {
                "accepted": False,
                "trigger_id": trigger_id,
                "reason": (
                "Unsupported trigger_id. Use an exact trigger_id from "
                "available_assessments."
        ),
        "available_assessments": public_scenario.get(
            "available_assessments",
            []
        )
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
@_logged_tool
def record_user_observation(
    field_id: str,
    value: str,
    unit: str = "",
    status: str = "known"
) -> dict[str, Any]:
    """
    Update current_patient.json with a new observation supplied directly by the clinician or user.
    Add the completed trigger ID to completed_triggers list if the observation corresponds to a trigger in the simulation.json.
    An example is ""completed_triggers": ["measure_spo2"]"

    Add any patient vitals and other observations to the clinical_data dictionary in current_patient.json in this format:
    "clinical_data": {
        "spo2": {
            "value": 95,
            "unit": "%",
            "status": "known",
            "source": "user"
        }
    }"
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
    
# here's our singular public neo4j tool and all necessary imports
from neo4j_logistics.neo4j_client import (
    Neo4jClient,
    Neo4jClientError,
    )
from neo4j_logistics.clinical_knowledge_repo import ClinicalKnowledgeRepo
from neo4j_logistics.clinical_guideline_service import ClinicalGuidanceService

neo4j_client = Neo4jClient()

knowledge_repo = ClinicalKnowledgeRepo(
    neo4j_client
)

guidance = ClinicalGuidanceService(
    knowledge_repo
)

@mcp.tool()
@_logged_tool
def get_clinical_guidance(
    task: str = "differential",
) -> dict[str, Any]:
    """
    Retrieve graph-supported clinical guidance using findings already
    recorded in the current patient state.

    The user does not need to manually advance workflow stages.

    For task="differential":
    - Read visible findings from the current patient state.
    - Retrieve graph-supported Disease and Condition candidates.
    - Save the resulting differential to patient state.
    - Automatically update the workflow to differential_diagnosis when
      useful findings were evaluated.
    - Recommend either additional assessment or review of the differential.

    Result statuses:
    - insufficient_information:
      No usable abnormal findings are available. Continue assessment.

    - no_graph_matches:
      Useful findings exist, but the graph returned no candidates.
      The model may formulate a provisional differential, but it must
      clearly label it as model inference rather than graph-supported.

    - needs_more_information:
      Graph candidates were found, but the differential remains broad.
      Collect additional distinguishing information.

    - focused_differential:
      The graph-supported differential is focused enough to review.

    The absence of a graph match does not rule out a diagnosis.
    This tool must not use hidden simulation or evaluation data.
    """
    if task != "differential":
        return {
            "success": False,
            "task": task,
            "reason": f"Unsupported guidance task: {task}",
            "supported_tasks": ["differential"],
        }

    try:
        state = read_patient_state()
        scenario = read_public_scenario(state["scenario_id"])

        result = guidance.build_differential(
            patient_state=state,
            public_scenario=scenario,
        )

        if not result.get("success", False):
            return result

        # Save candidates and the latest guidance summary.
        updated_state = record_guidance_result(
            guidance_result=result
        )

        guidance_status = result.get(
            "status",
            "insufficient_information",
        )

        # Any useful differential attempt progresses the internal
        # workflow, including cases where the graph has no coverage.
        if guidance_status != "insufficient_information":
            updated_state = update_current_stage(
                "differential_diagnosis"
            )

        return {
            **result,
            "workflow": {
                "current_stage": updated_state.get(
                    "current_stage"
                ),
                "stage_history": updated_state.get(
                    "stage_history",
                    [],
                ),
                "recommended_next_step": result.get(
                    "recommended_next_step"
                ),
            },
            "support": {
                "graph_supported": (
                    result.get("candidate_count", 0) > 0
                ),
                "candidate_count": result.get(
                    "candidate_count",
                    0,
                ),
                "warning": (
                    None
                    if result.get("candidate_count", 0) > 0
                    else (
                        "No graph-supported candidates were found. "
                        "Any provisional differential must be labeled "
                        "as model inference."
                    )
                ),
            },
        }

    except (StateManagerError, Neo4jClientError) as error:
        return {
            "success": False,
            "task": task,
            "reason": str(error),
        }
    
@mcp.tool()
@_logged_tool
def resolve_graph_candidate(
    candidate_name: str,
) -> dict[str, Any]:
    """
    Resolve an exact clinical name to a Disease or Condition node.

    Disease is searched first. Condition is searched only when no Disease
    has the requested case-insensitive exact name. This tool does not perform
    fuzzy matching or infer a diagnosis.
    """
    try:
        candidate = knowledge_repo.find_candidate_by_name(
            candidate_name
        )

        if candidate is None:
            return {
                "found": False,
                "query": candidate_name,
                "candidate": None,
                "search_order": [
                    "Disease",
                    "Condition",
                ],
                "reason": (
                    "No exact Disease or Condition name matched."
                ),
            }

        return {
            "found": True,
            "query": candidate_name,
            "candidate": candidate,
            "search_order": [
                "Disease",
                "Condition",
            ],
            "provenance": "Neo4j exact-name resolution",
        }

    except Neo4jClientError as error:
        return {
            "found": False,
            "query": candidate_name,
            "candidate": None,
            "search_order": [
                "Disease",
                "Condition",
            ],
            "reason": str(error),
        }

@mcp.tool()
@_logged_tool
def get_medkit_treatment_options(
    candidate_id: str,
    candidate_type: str,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Return only exact MedKit nodes connected to a resolved Disease or
    Condition candidate.

    candidate_id and candidate_type must come from
    resolve_graph_candidate. Treat the returned options as a closed-world
    list. Never add treatments that are absent from the result.
    """
    if candidate_type not in {"Disease", "Condition"}:
        return {
            "success": False,
            "candidate_id": candidate_id,
            "candidate_type": candidate_type,
            "reason": (
                "candidate_type must be Disease or Condition."
            ),
            "closed_world": True,
        }

    try:
        safe_limit = max(1, min(int(limit), 50))

        options = knowledge_repo.find_medkit_treatment_options(
            candidate_id=candidate_id,
            candidate_type=candidate_type,
            limit=safe_limit,
        )

        return {
            "success": True,
            "candidate_id": candidate_id,
            "candidate_type": candidate_type,
            "option_count": len(options),
            "options": options,
            "closed_world": True,
            "provenance": {
                "source": "Neo4j",
                "node_label": "MedKit",
                "allowed_relationships": [
                    "MAPSTO_CmD",
                    "TREATS_MKtC",
                    "ASSISTSTREATMENT_MKaC",
                    "INCLUDES_MKiMK",
                ],
            },
            "model_instruction": (
                "Return only exact options from this result."
                if options
                else (
                    "No graph-supported MedKit treatment options "
                    "were found. Do not add treatments from general "
                    "medical knowledge."
                )
            ),
            "warning": (
                "Graph presence does not independently verify physical "
                "availability or clinical appropriateness."
            ),
        }

    except (Neo4jClientError, ValueError) as error:
        return {
            "success": False,
            "candidate_id": candidate_id,
            "candidate_type": candidate_type,
            "reason": str(error),
            "closed_world": True,
        }

if __name__ == "__main__":
    #print("Starting CDSS MCP Server...", flush=True)
    _log_event(
        "server_start",
        server="CDSS MCP Server",
        transport="stdio",
    )
    mcp.run(transport="stdio")
