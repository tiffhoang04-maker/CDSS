# this file is used to locate and read stuff
# i am separating it from server.py so that it's less confusing

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
SCENARIOS_DIR = BASE_DIR / "scenarios"
PERSONAS_DIR = BASE_DIR / "personas"


class CaseRepositoryError(Exception):
    """Raised when a persona or scenario fixture cannot be loaded."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise CaseRepositoryError(f"File not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise CaseRepositoryError(
            f"Invalid JSON in {path}: {error}"
        ) from error

    if not isinstance(data, dict):
        raise CaseRepositoryError(
            f"Expected a JSON object in {path}."
        )

    return data


def read_public_scenario(scenario_id: str) -> dict[str, Any]:
    BASE_DIR = Path(__file__).resolve().parent.parent
    SCENARIOS_DIR = BASE_DIR / "scenarios"
    path = SCENARIOS_DIR / scenario_id / "public.json"
    scenario = _read_json(path)

    if scenario.get("scenario_id") != scenario_id:
        raise CaseRepositoryError(
            f"scenario_id mismatch in {path}"
        )

    return scenario


def read_simulation_scenario(scenario_id: str) -> dict[str, Any]:
    BASE_DIR = Path(__file__).resolve().parent.parent
    SCENARIOS_DIR = BASE_DIR / "scenarios"
    path = SCENARIOS_DIR / scenario_id / "simulation.json"
    scenario = _read_json(path)

    if scenario.get("scenario_id") != scenario_id:
        raise CaseRepositoryError(
            f"scenario_id mismatch in {path}"
        )

    return scenario


def read_evaluation_scenario(scenario_id: str) -> dict[str, Any]:
    BASE_DIR = Path(__file__).resolve().parent.parent
    SCENARIOS_DIR = BASE_DIR / "scenarios"
    path = SCENARIOS_DIR / scenario_id / "evaluation.json"
    scenario = _read_json(path)

    if scenario.get("scenario_id") != scenario_id:
        raise CaseRepositoryError(
            f"scenario_id mismatch in {path}"
        )

    return scenario


def read_persona(persona_id: str) -> dict[str, Any]:
    BASE_DIR = Path(__file__).resolve().parent.parent
    PERSONAS_DIR = BASE_DIR / "personas"
    path = PERSONAS_DIR / f"{persona_id}.json"
    persona = _read_json(path)

    if persona.get("persona_id") != persona_id:
        raise CaseRepositoryError(
            f"persona_id mismatch in {path}"
        )

    return persona