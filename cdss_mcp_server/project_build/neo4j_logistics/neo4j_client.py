from __future__ import annotations
import os
from typing import Any
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ENV_FILE)

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
        try:
            with self.driver.session(
                database=self.database
            ) as session:
                result = session.run(
                    query,
                    params or {}
                )
                return [
                    record.data()
                    for record in result
                ]

        except Neo4jError as error:
            raise Neo4jClientError(
                f"Neo4j query failed: {error}"
            ) from error

    def close(self) -> None:
        self.driver.close()