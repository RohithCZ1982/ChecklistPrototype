"""Inspection creation and retrieval."""

from __future__ import annotations

from typing import Dict, List, Optional

from modules.database import (
    add_inspection,
    get_inspection,
    list_inspections,
)


def save_inspection(
    name: str,
    checklist_id: str,
    checklist_name: str,
    inspection_date: str,
    results: Dict,
) -> str:
    return add_inspection(name, checklist_id, checklist_name, inspection_date, results)


def get_all_inspections(checklist_id: Optional[str] = None) -> List[Dict]:
    return list_inspections(checklist_id)


def get_inspection_detail(inspection_id: str) -> Optional[Dict]:
    return get_inspection(inspection_id)
