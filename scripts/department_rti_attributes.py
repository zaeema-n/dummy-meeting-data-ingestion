"""
Write rti_statuses tabular attributes onto resolved department entities.
"""

from __future__ import annotations

from typing import Any, Dict

from exceptions.exceptions import NotFoundError
from models.schema import EntityCreate
from services.ingestion_service import IngestionService
from services.read_service import ReadService
from utils.logger import logger
from utils.util_functions import Util

RTI_ATTRIBUTE_KEY = "rti_statuses"

RTI_COLUMNS = [
    "rti_request_id",
    "status",
    "direction",
    "date",
    "description",
    "files",
]

RTI_STATUSES_BY_DEPARTMENT: Dict[str, Dict[str, Any]] = {
    "UGC": {
        "columns": RTI_COLUMNS,
        "rows": [
            [
                "100001",
                "DELIVERY",
                "sent",
                "10/04/2026",
                "RTI request sent to UGC: last 6 meeting dates, meeting minutes, and board member list.",
                '["clarifications/RDA_query.pdf"]',
            ],
            [
                "100001",
                "ACKNOWLEDGE",
                "received",
                "20/04/2026",
                "Acknowledgement received from rti@ugc.com.",
                None,
            ],
            [
                "100001",
                "ACCEPTED",
                "received",
                "20/04/2026",
                "Request accepted.",
                None,
            ],
            [
                "100001",
                "DELIVERY",
                "received",
                "21/05/2026",
                "Partial response received.",
                None,
            ],
            [
                "100001",
                "COMPLETED",
                "received",
                "21/05/2026",
                "Request completed (partial): last 6 meeting dates and board members provided; meeting minutes not included.",
                '["requests/req_003.pdf"]',
            ],
        ],
    },
    "TVEC": {
        "columns": RTI_COLUMNS,
        "rows": [
            [
                "100002",
                "DELIVERY",
                "sent",
                "10/04/2026",
                "RTI request sent to TVEC: last 3 meeting dates, meeting minutes, and board member list.",
                '["clarifications/RDA_query.pdf"]',
            ],
            [
                "100002",
                "ACKNOWLEDGEMENT",
                "received",
                "17/04/2026",
                "Acknowledgement received.",
                None,
            ],
            [
                "100002",
                "ACCEPTED",
                "received",
                "17/04/2026",
                "Request accepted.",
                None,
            ],
            [
                "100002",
                "DELIVERY",
                "received",
                "27/04/2026",
                "Full response received: all requested data.",
                None,
            ],
            [
                "100002",
                "COMPLETED",
                "received",
                "27/04/2026",
                "Request completed: all requested data received.",
                '["requests/req_003.pdf"]',
            ],
        ],
    },
    "OMP": {
        "columns": RTI_COLUMNS,
        "rows": [
            [
                "100003",
                "DELIVERY",
                "sent",
                "10/04/2026",
                "RTI request sent to OMP: last 3 meeting dates, meeting minutes, and board member list.",
                '["clarifications/RDA_query.pdf"]',
            ],
            [
                "100003",
                "DELIVERY",
                "received",
                "11/04/2026",
                "Partial response received.",
                None,
            ],
            [
                "100003",
                "COMPLETED",
                "received",
                "11/04/2026",
                "Request completed (partial): last 3 meeting dates and board members provided; meeting minutes not included.",
                '["requests/req_003.pdf"]',
            ],
        ],
    },
    "DMC": {
        "columns": RTI_COLUMNS,
        "rows": [
            [
                "100004",
                "DELIVERY",
                "sent",
                "10/04/2026",
                "RTI request sent to DMC: last 3 meeting dates, meeting minutes, and board member list.",
                '["clarifications/RDA_query.pdf"]',
            ],
            [
                "100004",
                "ACKNOWLEDGE",
                "received",
                "17/04/2026",
                "Acknowledgement received.",
                None,
            ],
            [
                "100004",
                "REJECTED",
                "received",
                "27/04/2026",
                "Request rejected: requested data is confidential.",
                None,
            ],
            [
                "100004",
                "COMPLETED",
                "received",
                "27/04/2026",
                "Request closed: rejected as confidential.",
                '["requests/req_003.pdf"]',
            ],
        ],
    },
}


def build_rti_attribute(
    data_content: dict,
    start_time: str,
    end_time: str = "",
) -> dict:
    """Build OpenGIN attribute payload for rti_statuses."""
    return {
        "key": RTI_ATTRIBUTE_KEY,
        "value": {
            "values": [
                {
                    "startTime": start_time,
                    "endTime": end_time,
                    "value": data_content,
                }
            ]
        },
    }


def _attribute_exists_for_start_time(existing: object, start_time: str) -> bool:
    """Return True if read response already has a value slice for start_time."""
    if not isinstance(existing, dict):
        return False

    body = existing.get("body", existing)
    if not isinstance(body, dict):
        return False

    value_wrapper = body.get("value")
    if not isinstance(value_wrapper, dict):
        return False

    values = value_wrapper.get("values")
    if not isinstance(values, list):
        return False

    for entry in values:
        if isinstance(entry, dict) and entry.get("startTime") == start_time:
            return True
    return False


async def write_department_rti_attributes(
    ingestion_service: IngestionService,
    read_service: ReadService,
    department_ids: Dict[str, str],
    start_time: str,
) -> None:
    """Write rti_statuses attribute for each resolved department (one PUT each)."""
    for department_code, data_content in RTI_STATUSES_BY_DEPARTMENT.items():
        department_id = department_ids.get(department_code)
        if not department_id:
            raise RuntimeError(f"Missing department id for code={department_code}")

        if not Util.validate_tabular_dataset(data_content):
            raise RuntimeError(
                f"Invalid tabular data for department {department_code} rti_statuses"
            )

        try:
            existing = await read_service.get_entity_attribute(
                department_id,
                RTI_ATTRIBUTE_KEY,
                startTime=start_time,
            )
            if _attribute_exists_for_start_time(existing, start_time):
                logger.info(
                    "Skipping %s id=%s: %s already set for startTime=%s",
                    department_code,
                    department_id,
                    RTI_ATTRIBUTE_KEY,
                    start_time,
                )
                continue
        except NotFoundError:
            pass

        attribute = build_rti_attribute(data_content, start_time)
        payload = EntityCreate(id=department_id, attributes=[attribute])
        await ingestion_service.update_entity(department_id, payload)
        logger.info(
            "Updated %s id=%s: attribute %s (%d rows)",
            department_code,
            department_id,
            RTI_ATTRIBUTE_KEY,
            len(data_content["rows"]),
        )
