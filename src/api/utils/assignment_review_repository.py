#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Assignment Review repository abstraction.

Phase 6 storage evolution baseline:
- Keep JSON-compatible persistence
- Decouple store workflow from concrete storage backend
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol


class AssignmentReviewRepository(Protocol):
    def init_json_file(self, path: Path, initial_payload: dict[str, Any]) -> None: ...

    def read_json(self, path: Path) -> dict[str, Any]: ...

    def write_json(self, path: Path, payload: dict[str, Any]) -> None: ...


class JsonAssignmentReviewRepository:
    """JSON file-backed repository implementation."""

    def init_json_file(self, path: Path, initial_payload: dict[str, Any]) -> None:
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(initial_payload, f, indent=2, ensure_ascii=False)

    def read_json(self, path: Path) -> dict[str, Any]:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}

    def write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            suffix=f"{path.suffix}.tmp",
        ) as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
            temp_path = Path(f.name)
        os.replace(temp_path, path)
