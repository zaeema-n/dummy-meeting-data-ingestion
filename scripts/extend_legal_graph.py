"""
Hardcoded script to extend the legal graph in OpenGIN.

This file currently implements only the first setup step:
- hardcoded node and edge definitions
- TODAY constant
- async http_client bootstrap/shutdown
- asyncio main entrypoint
"""

from __future__ import annotations

import asyncio
from datetime import date

from models.schema import Kind
from services.ingestion_service import IngestionService
from services.read_service import ReadService
from utils.http_client import http_client
from utils.logger import logger


# Runtime date used across relation/attribute temporal fields.
TODAY = date.today().isoformat()


# Root person used to discover ministries through AS_MINISTER.
PERSON_ROOT = {
    "name": "Anura Kumara Dissanayake",
    "kind": Kind(major="Person", minor="citizen"),
}


# Expected ministry names discovered from PERSON_ROOT via AS_MINISTER.
EXPECTED_MINISTRIES = {
    "MOE": "Minister of Education, Higher Education and Vocational Education",
    "MOJ": "Minister of Justice and National Integration",
    "MOD": "Minister of Defence",
}


# Expected departments discovered from each ministry via AS_DEPARTMENT.
EXPECTED_DEPARTMENTS_BY_MINISTRY = {
    "MOE": [
        "University Grants Commission",
        "Tertiary and Vocational Education Commission",
    ],
    "MOJ": [
        "Office on Missing Persons",
    ],
    "MOD": [
        "National Disaster Management Council",
    ],
}


# New nodes to create in graph.
NEW_NODES = {
    "UGC_Act": {"name": "Universities Act", "major": "Document", "minor": "act"},
    "Comm_Mtg": {"name": "Commission Meeting", "major": "Event", "minor": "meeting"},
    "TVEC_Act": {
        "name": "Tertiary and Vocational Education Act, No. 20 of 1990",
        "major": "Document",
        "minor": "act",
    },
    "TVEC_Mtg": {"name": "Commission Meeting", "major": "Event", "minor": "meeting"},
    "OMP_Act": {
        "name": "Office on Missing Persons Act, No. 14 of 2016",
        "major": "Document",
        "minor": "act",
    },
    "Board_Mtg": {"name": "Board Meeting", "major": "Event", "minor": "meeting"},
    "DM_Act": {"name": "DM Act", "major": "Document", "minor": "act"},
    "Council_Mtg": {"name": "Council Meeting", "major": "Event", "minor": "meeting"},
}


# Edge definitions: source_key, relationship_key, target_key.
EDGE_DEFINITIONS = [
    ("UGC_Act", "MANDATES", "UGC"),
    ("UGC_Act", "MANDATES", "Comm_Mtg"),
    ("UGC", "HAS_EVENT", "Comm_Mtg"),
    ("MOE", "AS_DEPARTMENT", "UGC"),
    ("MOE", "AS_DEPARTMENT", "TVEC"),
    ("TVEC_Act", "MANDATES", "TVEC"),
    ("TVEC_Act", "MANDATES", "TVEC_Mtg"),
    ("TVEC", "HAS_EVENT", "TVEC_Mtg"),
    ("MOJ", "AS_DEPARTMENT", "OMP"),
    ("OMP_Act", "MANDATES", "OMP"),
    ("OMP_Act", "MANDATES", "Board_Mtg"),
    ("OMP", "HAS_EVENT", "Board_Mtg"),
    ("MOD", "AS_DEPARTMENT", "DMC"),
    ("DM_Act", "MANDATES", "DMC"),
    ("DM_Act", "MANDATES", "Council_Mtg"),
    ("DMC", "HAS_EVENT", "Council_Mtg"),
]


async def run() -> None:
    """Bootstrap clients and print scaffold status."""
    await http_client.start()
    try:
        # Service instances are initialized now; next todos will use them.
        read_service = ReadService()
        ingestion_service = IngestionService()

        logger.info("extend_legal_graph scaffold ready.")
        logger.info("TODAY=%s", TODAY)
        logger.info("Loaded %d new node definitions.", len(NEW_NODES))
        logger.info("Loaded %d edge definitions.", len(EDGE_DEFINITIONS))

        # Prevent lint warnings for currently-unused service instances.
        _ = (read_service, ingestion_service)
    finally:
        await http_client.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
