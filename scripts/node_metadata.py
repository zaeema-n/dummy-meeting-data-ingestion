"""
Load act and meeting metadata from data/*.json, substitute node_id placeholders,
and write OpenGIN metadata (key/value array) onto graph entities.
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List

from models.schema import EntityCreate
from services.ingestion_service import IngestionService
from services.read_service import ReadService
from utils.logger import logger

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACT_METADATA_PATH = os.path.join(PROJECT_ROOT, "data", "act_metadata.json")
MEETING_METADATA_PATH = os.path.join(PROJECT_ROOT, "data", "meeting_metadata.json")

PLACEHOLDER_TO_ENTITY_KEY = {
    "UGC_NODE_ID": "UGC",
    "TVEC_NODE_ID": "TVEC",
    "OMP_NODE_ID": "OMP",
    "DMC_NODE_ID": "DMC",
    "UGC_COMM_MEETING_NODE_ID": "Comm_Mtg",
    "TVEC_MEETING_NODE_ID": "TVEC_Mtg",
    "OMP_MEETING_NODE_ID": "Board_Mtg",
    "DMC_MEETING_NODE_ID": "Council_Mtg",
}

def load_metadata_file(path: str) -> List[Dict[str, Any]]:
    """Load metadata entries from a JSON array file."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise RuntimeError(f"Expected JSON array in {path}")
    return data


def build_placeholder_id_map(all_entity_ids: Dict[str, str]) -> Dict[str, str]:
    """Map placeholder strings to resolved entity IDs."""
    id_map: Dict[str, str] = {}
    for placeholder, entity_key in PLACEHOLDER_TO_ENTITY_KEY.items():
        entity_id = all_entity_ids.get(entity_key)
        if not entity_id:
            raise RuntimeError(
                f"Missing entity id for placeholder {placeholder} (key={entity_key})"
            )
        id_map[placeholder] = entity_id
    return id_map


def to_opengin_metadata_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize metadata to OpenGIN format: [{"key": "...", "value": ...}, ...].
    Accepts items already in key/value form or legacy single-object entries.
    """
    result: List[Dict[str, Any]] = []
    for item in items:
        if "key" in item and "value" in item:
            result.append({"key": item["key"], "value": item["value"]})
            continue
        for key, value in item.items():
            result.append({"key": key, "value": value})
    if not result:
        raise RuntimeError("metadata must contain at least one key/value entry")
    return result


def normalize_metadata_for_ingest(metadata: Any) -> List[Dict[str, Any]]:
    """Ensure metadata is a non-empty OpenGIN key/value array."""
    if isinstance(metadata, dict):
        if "key" in metadata and "value" in metadata:
            return [metadata]
        return to_opengin_metadata_items([metadata])
    if isinstance(metadata, list):
        if not metadata:
            raise RuntimeError("metadata array must not be empty")
        return to_opengin_metadata_items(metadata)
    raise RuntimeError(f"metadata must be an array or object, got {type(metadata).__name__}")


def substitute_node_ids(obj: Any, id_map: Dict[str, str]) -> Any:
    """Recursively replace placeholder string values with real entity IDs."""
    if isinstance(obj, dict):
        return {key: substitute_node_ids(value, id_map) for key, value in obj.items()}
    if isinstance(obj, list):
        return [substitute_node_ids(item, id_map) for item in obj]
    if isinstance(obj, str) and obj in id_map:
        return id_map[obj]
    return obj


def build_metadata_update_payload(
    entity_id: str,
    metadata: List[Dict[str, Any]],
) -> EntityCreate:
    """Build minimal EntityCreate for metadata-only PUT (id + metadata only)."""
    return EntityCreate(id=entity_id, metadata=metadata)


def _metadata_exists(existing: object) -> bool:
    """Return True if read response already contains metadata."""
    if existing is None:
        return False

    if isinstance(existing, list):
        return len(existing) > 0

    if not isinstance(existing, dict):
        return False

    body = existing.get("body", existing)
    if isinstance(body, list):
        return len(body) > 0
    if isinstance(body, dict):
        if body.get("metadata"):
            metadata = body["metadata"]
            if isinstance(metadata, list):
                return len(metadata) > 0
            return bool(metadata)
        return bool(body)
    return False


async def _write_metadata_entries(
    ingestion_service: IngestionService,
    read_service: ReadService,
    all_entity_ids: Dict[str, str],
    metadata_path: str,
    label: str,
) -> None:
    """Load metadata file entries and write one PUT per entity."""
    entries = load_metadata_file(metadata_path)
    id_map = build_placeholder_id_map(all_entity_ids)

    for entry in entries:
        entity_key = entry.get("entity_key")
        raw_metadata = entry.get("metadata")
        if not entity_key or raw_metadata is None:
            raise RuntimeError(f"Invalid metadata entry in {metadata_path}: {entry}")

        metadata_list = normalize_metadata_for_ingest(raw_metadata)

        entity_id = all_entity_ids.get(entity_key)
        if not entity_id:
            raise RuntimeError(f"Missing entity id for key={entity_key}")

        existing = await read_service.get_entity_metadata(entity_id)
        if _metadata_exists(existing):
            logger.info(
                "Skipping %s id=%s: metadata already exists",
                entity_key,
                entity_id,
            )
            continue

        resolved_metadata = substitute_node_ids(
            copy.deepcopy(metadata_list),
            id_map,
        )
        payload = build_metadata_update_payload(entity_id, resolved_metadata)
        await ingestion_service.update_entity(entity_id, payload)
        logger.info("Updated %s id=%s: metadata (%s)", entity_key, entity_id, label)


async def write_act_metadata(
    ingestion_service: IngestionService,
    read_service: ReadService,
    all_entity_ids: Dict[str, str],
) -> None:
    """Write act metadata for UGC_Act, TVEC_Act, OMP_Act, DM_Act."""
    await _write_metadata_entries(
        ingestion_service,
        read_service,
        all_entity_ids,
        ACT_METADATA_PATH,
        "act",
    )


async def write_meeting_metadata(
    ingestion_service: IngestionService,
    read_service: ReadService,
    all_entity_ids: Dict[str, str],
) -> None:
    """Write meeting metadata for Comm_Mtg, TVEC_Mtg, Board_Mtg."""
    await _write_metadata_entries(
        ingestion_service,
        read_service,
        all_entity_ids,
        MEETING_METADATA_PATH,
        "meeting",
    )
