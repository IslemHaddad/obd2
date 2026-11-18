"""Saved adapters: identity, chip profile, learned voltmeter correction, last use."""
from __future__ import annotations

from datetime import datetime

from .store import Store


def key_for(kind: str, arg) -> str:
    if kind == "serial":
        return f"serial:{arg[0]}"
    if kind == "tcp":
        return f"tcp:{arg[0]}:{arg[1]}"
    return f"{kind}:{arg}"


def all_adapters(store: Store) -> list[dict]:
    return sorted(store.get("adapters") or [], key=lambda a: a.get("last_used", ""), reverse=True)


def get(store: Store, key: str) -> dict | None:
    return next((a for a in store.get("adapters") or [] if a["key"] == key), None)


def remember(store: Store, kind: str, arg, name: str, profile) -> dict:
    k = key_for(kind, arg)
    items = [a for a in store.get("adapters") or [] if a["key"] != k]
    old = get(store, k) or {}
    rec = {"key": k, "kind": kind, "arg": list(arg) if isinstance(arg, tuple) else arg,
           "name": old.get("name") or name, "chip": profile.chip, "summary": profile.summary,
           "stn": profile.is_stn, "clone": profile.is_clone, "volt_offset": old.get("volt_offset"),
           "last_used": datetime.now().isoformat(timespec="seconds")}
    items.append(rec)
    store.set("adapters", items)
    return rec


def learn_voltage(store: Store, key: str, adapter_v: float, car_v: float) -> float | None:
    """Exponential average of (adapter voltmeter − car's own voltage)."""
    items = store.get("adapters") or []
    for a in items:
        if a["key"] == key:
            d = adapter_v - car_v
            a["volt_offset"] = d if a.get("volt_offset") is None else a["volt_offset"] * 0.8 + d * 0.2
            store.set("adapters", items)
            return a["volt_offset"]
    return None


def forget(store: Store, key: str) -> None:
    store.set("adapters", [a for a in store.get("adapters") or [] if a["key"] != key])
