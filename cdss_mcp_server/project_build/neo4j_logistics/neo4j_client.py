from __future__ import annotations
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ENV_FILE)

logger = logging.getLogger("cdss_mcp_server")

class Neo4jClientError(RuntimeError):
    """Raised when the Neo4j client cannot connect or run a query."""

class Neo4jClient: 
    def __init__(self) -> None:
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.username = os.getenv("NEO4J_USERNAME", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD")
        self.database = os.getenv("NEO4J_DATABASE", "integrated")

        if not self.password:
            raise Neo4jClientError(
                "NEO4J_PASSWORD is missing from .env"
            )
        
        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.username, self.password)
        )

    def verify_connectivity(self) -> None:
        try:
            self.driver.verify_connectivity()
        except Neo4jError as error:
            raise Neo4jClientError(
                f"Unable to connect to Neo4j: {error}"
            ) from error

    def run_query(
        self,
        query: str,
        params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        started_at = time.perf_counter()
        normalized_query = " ".join(query.split())
        safe_params = {
            key: value
            for key, value in (params or {}).items()
            if not any(
                sensitive in key.lower()
                for sensitive in ("password", "secret", "token")
            )
        }
        logger.info(
            json.dumps(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": "neo4j_query_start",
                    "query": normalized_query,
                    "params": safe_params,
                },
                default=str,
                sort_keys=True,
            )
        )

        try:
            with self.driver.session(
                database=self.database
            ) as session:
                result = session.run(
                    query,
                    params or {}
                )
                rows = [
                    record.data()
                    for record in result
                ]
                logger.info(
                    json.dumps(
                        {
                            "timestamp": datetime.now(
                                timezone.utc
                            ).isoformat(),
                            "event": "neo4j_query_end",
                            "duration_ms": round(
                                (
                                    time.perf_counter()
                                    - started_at
                                )
                                * 1000,
                                2,
                            ),
                            "row_count": len(rows),
                        },
                        sort_keys=True,
                    )
                )
                return rows

        except Neo4jError as error:
            logger.info(
                json.dumps(
                    {
                        "timestamp": datetime.now(
                            timezone.utc
                        ).isoformat(),
                        "event": "neo4j_query_exception",
                        "duration_ms": round(
                            (time.perf_counter() - started_at)
                            * 1000,
                            2,
                        ),
                        "error_type": type(error).__name__,
                        "error": str(error),
                    },
                    sort_keys=True,
                )
            )
            raise Neo4jClientError(
                f"Neo4j query failed: {error}"
            ) from error

    def close(self) -> None:
        self.driver.close()
