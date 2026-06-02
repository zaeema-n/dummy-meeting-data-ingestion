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
from typing import Dict

from models.schema import Entity, Kind, Relation
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


async def resolve_entity_by_name(
    read_service: ReadService,
    name: str,
    major: str,
    minor: str,
) -> Entity:
    """Find one entity by exact name and kind."""
    matches = await read_service.get_entities(
        Entity(name=name, kind=Kind(major=major, minor=minor))
    )
    if not matches:
        raise RuntimeError(f"Entity not found: {name} ({major}/{minor})")
    if len(matches) > 1:
        logger.warning(
            "Multiple matches for %s (%s/%s); using first id=%s",
            name,
            major,
            minor,
            matches[0].id,
        )
    return matches[0]


async def resolve_entity_by_id(read_service: ReadService, entity_id: str) -> Entity:
    """Find one entity by ID via the search endpoint."""
    matches = await read_service.get_entities(Entity(id=entity_id))
    if not matches:
        raise RuntimeError(f"Entity not found by id: {entity_id}")
    if len(matches) > 1:
        logger.warning("Multiple matches for id=%s; using first", entity_id)
    return matches[0]


async def resolve_ministry_ids_from_person(read_service: ReadService) -> Dict[str, str]:
    """
    Resolve MOE/MOJ/MOD ministry IDs from person -> AS_MINISTER relations at TODAY.
    """
    person = await resolve_entity_by_name(
        read_service,
        PERSON_ROOT["name"],
        PERSON_ROOT["kind"].major,
        PERSON_ROOT["kind"].minor,
    )
    logger.info("Resolved root person id=%s", person.id)

    minister_rels = await read_service.fetch_relations(
        person.id,
        Relation(name="AS_MINISTER", activeAt=TODAY),
    )
    if not minister_rels:
        raise RuntimeError(
            f"No AS_MINISTER relations found for person id={person.id} at activeAt={TODAY}"
        )

    expected_by_name: Dict[str, str] = {
        expected_name: code for code, expected_name in EXPECTED_MINISTRIES.items()
    }
    mapped: Dict[str, str] = {}
    for rel in minister_rels:
        ministry = await resolve_entity_by_id(read_service, rel.relatedEntityId)
        code = expected_by_name.get(ministry.name)
        if code:
            mapped[code] = ministry.id

    missing_keys = [code for code in EXPECTED_MINISTRIES if code not in mapped]

    if missing_keys:
        raise RuntimeError(
            "Missing expected ministries from AS_MINISTER traversal: "
            + ", ".join(f"{code}: {EXPECTED_MINISTRIES[code]}" for code in missing_keys)
        )
    return mapped


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
        ministry_ids = await resolve_ministry_ids_from_person(read_service)
        logger.info("Resolved ministries from person traversal: %s", ministry_ids)

        # Prevent lint warnings for currently-unused service instances.
        _ = ingestion_service
    finally:
        await http_client.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
