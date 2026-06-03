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
import os
import sys
from datetime import date
from typing import Dict
from uuid import uuid4

# Allow direct execution: `python extend_legal_graph.py` from scripts/ directory.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from models.schema import (
    AddRelation,
    AddRelationValue,
    Entity,
    EntityCreate,
    Kind,
    NameValue,
    Relation,
)
from services.ingestion_service import IngestionService
from services.read_service import ReadService
from utils.http_client import http_client
from utils.logger import logger
from utils.util_functions import Util

from department_rti_attributes import write_department_rti_attributes


# Runtime date used across relation/attribute temporal fields.
TODAY = date.today().isoformat()
NOW_TS = f"{TODAY}T00:00:00Z"


# Root person used to discover ministries through AS_MINISTER.
PERSON_ROOT = {
    "name": "Anura Kumara Dissanayake",
    "kind": Kind(major="Person", minor="citizen"),
}


# Expected ministry names discovered from PERSON_ROOT via AS_MINISTER.
EXPECTED_MINISTRIES = [
    "Minister of Education, Higher Education and Vocational Education",
    "Minister of Justice and National Integration",
    "Minister of Defence",
]

# Short ministry references used by EDGE_DEFINITIONS.
MINISTRY_CODES_BY_NAME = {
    "Minister of Education, Higher Education and Vocational Education": "MOE",
    "Minister of Justice and National Integration": "MOJ",
    "Minister of Defence": "MOD",
}


# Expected departments discovered from each ministry via AS_DEPARTMENT.
EXPECTED_DEPARTMENTS_BY_MINISTRY = {
    "Minister of Education, Higher Education and Vocational Education": [
        "University Grants Commission",
        "Tertiary and Vocational Education Commission",
    ],
    "Minister of Justice and National Integration": [
        "Office on Missing Persons",
    ],
    "Minister of Defence": [
        "National Disaster Management Council",
    ],
}

# Short department references used by EDGE_DEFINITIONS.
DEPARTMENT_CODES_BY_NAME = {
    "University Grants Commission": "UGC",
    "Tertiary and Vocational Education Commission": "TVEC",
    "Office on Missing Persons": "OMP",
    "National Disaster Management Council": "DMC",
}


# New nodes to create in graph.
NEW_NODES = {
    "UGC_Act": {"name": "Universities Act, No. 16 of 1978", "major": "Document", "minor": "act"},
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
    "DM_Act": {"name": "Disaster Management Act, No. 13 of 2005", "major": "Document", "minor": "act"},
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


def decode_entity_name(raw_name: str) -> str:
    """Decode protobuf-encoded name payloads; fallback to raw string."""
    decoded = Util.decode_protobuf_attribute_name(raw_name)
    if decoded and decoded != "Unknown":
        return decoded
    return raw_name


async def resolve_ministry_ids_from_person(read_service: ReadService) -> Dict[str, str]:
    """
    Resolve ministry IDs from person -> AS_MINISTER relations at TODAY.
    Returns ids keyed by short ministry codes (MOE/MOJ/MOD).
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

    mapped_by_name: Dict[str, str] = {}
    for rel in minister_rels:
        ministry = await resolve_entity_by_id(read_service, rel.relatedEntityId)
        ministry_name = decode_entity_name(ministry.name)
        if ministry_name in EXPECTED_MINISTRIES:
            mapped_by_name[ministry_name] = ministry.id

    missing_ministries = [name for name in EXPECTED_MINISTRIES if name not in mapped_by_name]

    if missing_ministries:
        raise RuntimeError(
            "Missing expected ministries from AS_MINISTER traversal: "
            + ", ".join(missing_ministries)
        )

    mapped_by_code: Dict[str, str] = {}
    for ministry_name, ministry_id in mapped_by_name.items():
        ministry_code = MINISTRY_CODES_BY_NAME[ministry_name]
        mapped_by_code[ministry_code] = ministry_id

    return mapped_by_code


async def resolve_department_ids_from_ministries(
    read_service: ReadService,
    ministry_ids: Dict[str, str],
) -> Dict[str, str]:
    """
    Resolve departments via ministry -> AS_DEPARTMENT relations at TODAY.
    """
    department_ids_by_code: Dict[str, str] = {}

    for ministry_name, expected_department_names in EXPECTED_DEPARTMENTS_BY_MINISTRY.items():
        ministry_code = MINISTRY_CODES_BY_NAME[ministry_name]
        ministry_id = ministry_ids.get(ministry_code)
        if not ministry_id:
            raise RuntimeError(f"Missing ministry id for {ministry_name} ({ministry_code})")

        department_rels = await read_service.fetch_relations(
            ministry_id,
            Relation(name="AS_DEPARTMENT", activeAt=TODAY),
        )
        if not department_rels:
            raise RuntimeError(
                f"No AS_DEPARTMENT relations found for {ministry_name} id={ministry_id}"
            )

        expected_name_set = set(expected_department_names)
        found_names = set()
        for rel in department_rels:
            department = await resolve_entity_by_id(read_service, rel.relatedEntityId)
            department_name = decode_entity_name(department.name)
            if department_name not in expected_name_set:
                continue
            department_code = DEPARTMENT_CODES_BY_NAME.get(department_name)
            if not department_code:
                continue
            department_ids_by_code[department_code] = department.id
            found_names.add(department_name)

        missing_names = sorted(expected_name_set - found_names)
        if missing_names:
            raise RuntimeError(
                f"Missing expected AS_DEPARTMENT targets for {ministry_name}: {missing_names}"
            )

    expected_departments = {
        DEPARTMENT_CODES_BY_NAME[department_name]
        for department_names in EXPECTED_DEPARTMENTS_BY_MINISTRY.values()
        for department_name in department_names
    }
    missing_departments = sorted(expected_departments - set(department_ids_by_code.keys()))
    if missing_departments:
        raise RuntimeError(f"Missing resolved departments: {missing_departments}")

    return department_ids_by_code


def extract_entity_id_from_create_response(response: object) -> str:
    """Best-effort extraction of created entity id from API response payload."""
    if not isinstance(response, dict):
        return ""

    # Common OpenGIN-style wrapper: {"body": {...}}
    body = response.get("body")
    if isinstance(body, dict):
        entity_id = body.get("id")
        if isinstance(entity_id, str) and entity_id.strip():
            return entity_id.strip()

    # Some APIs may return id at top-level.
    top_level_id = response.get("id")
    if isinstance(top_level_id, str) and top_level_id.strip():
        return top_level_id.strip()

    return ""


async def create_new_entities(ingestion_service: IngestionService) -> Dict[str, str]:
    """
    Create new Document/act and Event/meeting entities.
    Returns ids keyed by NEW_NODES codes.
    """
    created_ids: Dict[str, str] = {}

    for node_key, node in NEW_NODES.items():
        unique_id = str(uuid4())
        payload = EntityCreate(
            id=unique_id,
            kind=Kind(major=node["major"], minor=node["minor"]),
            name=NameValue(
                startTime=NOW_TS,
                endTime="",
                value=node["name"],
            ),
            created=NOW_TS,
            terminated="",
            metadata=[],
            attributes=[],
            relationships=[],
        )
        response = await ingestion_service.create_entity(payload)
        entity_id = extract_entity_id_from_create_response(response)
        if not entity_id:
            # Some servers echo no body; fallback to the supplied id.
            entity_id = unique_id
        created_ids[node_key] = entity_id
        logger.info("Created %s (%s) id=%s", node_key, node["name"], entity_id)

    return created_ids


def build_relationship_id(source_id: str, relationship_name: str, target_id: str) -> str:
    """Create new relationship id."""
    _ = (source_id, relationship_name, target_id)
    return str(uuid4())


def build_relation(relationship_name: str, source_id: str, target_id: str) -> AddRelation:
    relationship_id = build_relationship_id(source_id, relationship_name, target_id)
    return AddRelation(
        key=relationship_name,
        value=AddRelationValue(
            relatedEntityId=target_id,
            startTime=TODAY,
            id=relationship_id,
            name=relationship_name,
        ),
    )


async def write_relationships(
    ingestion_service: IngestionService,
    all_entity_ids: Dict[str, str],
) -> None:
    """
    Write all graph edges.

    One PUT per relationship: OpenGIN currently overwrites duplicate keys
    (e.g. two MANDATES) when sent in a single update payload.
    """
    for source_key, relationship_name, target_key in EDGE_DEFINITIONS:
        source_id = all_entity_ids.get(source_key)
        target_id = all_entity_ids.get(target_key)
        if not source_id:
            raise RuntimeError(f"Missing source id for key={source_key}")
        if not target_id:
            raise RuntimeError(f"Missing target id for key={target_key}")

        relation = build_relation(relationship_name, source_id, target_id)
        payload = EntityCreate(id=source_id, relationships=[relation])
        await ingestion_service.update_entity(source_id, payload)
        logger.info(
            "Updated %s id=%s: %s -> %s",
            source_key,
            source_id,
            relationship_name,
            target_key,
        )


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
        department_ids = await resolve_department_ids_from_ministries(
            read_service,
            ministry_ids,
        )
        logger.info("Resolved departments from minister traversal: %s", department_ids)
        created_node_ids = await create_new_entities(ingestion_service)
        logger.info("Created new entities: %s", created_node_ids)
        all_entity_ids = {}
        all_entity_ids.update(ministry_ids)
        all_entity_ids.update(department_ids)
        all_entity_ids.update(created_node_ids)
        await write_relationships(ingestion_service, all_entity_ids)
        logger.info("Wrote %d relationships successfully.", len(EDGE_DEFINITIONS))
        await write_department_rti_attributes(
            ingestion_service,
            read_service,
            department_ids,
            NOW_TS,
        )
        logger.info(
            "Wrote rti_statuses for %d departments.",
            len(department_ids),
        )
    finally:
        await http_client.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
