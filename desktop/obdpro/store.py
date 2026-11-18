"""Tiny JSON persistence in the user's config dir."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path


def _dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    d = Path(base) / "obdpro"
    d.mkdir(parents=True, exist_ok=True)
    return d


class Store:
    """Keys: settings, measurements, backups, recipes, adaptations, output_tests, basic_settings, vehicle."""

    def __init__(self):
        self.path = _dir() / "store.json"
        try:
            self.data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default if default is not None else [])

    def set(self, key, value) -> None:
        self.data[key] = value
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1))
        tmp.replace(self.path)

    def items(self, key: str, module: str | None = None) -> list[dict]:
        v = self.get(key)
        return [x for x in v if module is None or x.get("module") == module]

    def upsert(self, key: str, item: dict) -> dict:
        item.setdefault("id", uuid.uuid4().hex)
        v = [x for x in self.get(key) if x.get("id") != item["id"]]
        v.append(item)
        self.set(key, v)
        return item

    def delete(self, key: str, item_id: str) -> None:
        self.set(key, [x for x in self.get(key) if x.get("id") != item_id])

    def prepend(self, key: str, item: dict) -> None:
        item.setdefault("id", uuid.uuid4().hex)
        self.set(key, [item] + self.get(key))

    @staticmethod
    def logs_dir() -> Path:
        d = Path.home() / "Documents" / "OBDPro"
        d.mkdir(parents=True, exist_ok=True)
        return d
