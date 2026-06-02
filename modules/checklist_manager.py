"""Checklist creation, storage, and retrieval."""

from __future__ import annotations

from typing import Dict, List, Optional

from modules.database import (
    add_checklist,
    delete_checklist,
    get_checklist,
    list_checklists,
    update_checklist,
)


def create_checklist(name: str, description: str, template_ids: List[str]) -> str:
    return add_checklist(name, description, template_ids)


def get_all_checklists() -> List[Dict]:
    return list_checklists()


def load_checklist(checklist_id: str) -> Optional[Dict]:
    return get_checklist(checklist_id)


def edit_checklist(checklist_id: str, name: str, description: str, template_ids: List[str]) -> None:
    update_checklist(checklist_id, name, description, template_ids)


def remove_checklist(checklist_id: str) -> None:
    delete_checklist(checklist_id)
