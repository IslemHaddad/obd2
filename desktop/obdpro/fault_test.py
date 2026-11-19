"""Fault Test: watch one module's fault memory live (~1×/s) while the user operates the system step by step.
Anything the module detects pops up with the step that triggered it. Shared by the desktop and Android apps."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from . import fault_info
from .elm import ELMError


@dataclass
class Hit:
    fault: object        # vag.Fault
    step: int
    at: float


@dataclass
class FaultTest:
    vag: object          # VAG or Hyundai
    module: object       # vag.Module
    clear_first: bool = True
    on_change: object = None          # called from the worker thread after every change
    steps: list = field(default_factory=list)
    step: int = 0
    phase: str = "preparing"          # preparing | clearing | watching | finished | error
    error: str = ""
    note: str = ""
    before: list = field(default_factory=list)
    hits: list = field(default_factory=list)
    last: list | None = None
    reads: int = 0

    def __post_init__(self):
        self.steps = fault_info.test_steps(self.module.name)
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self.phase in ("preparing", "clearing", "watching")

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def next(self):
        if self.step + 1 < len(self.steps):
            self.step += 1
            self._changed()

    def back(self):
        if self.step > 0:
            self.step -= 1
            self._changed()

    def finish(self):
        if self.running:
            self.phase = "finished"
            self._changed()

    def _changed(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:                                  # noqa: BLE001 — UI gone
                pass

    def _read(self):
        try:
            with self.vag.channel(self.module):
                return self.vag.faults_open(self.module)
        except ELMError:
            return None

    def _run(self):
        if self.clear_first:
            self.phase = "clearing"
            self._changed()
            try:
                self.vag.clear(self.module)
            except ELMError as e:
                self.note = f"Couldn't clear first ({e}) — watching anyway."
        first = self._read()
        if first is None:
            self.phase, self.error = "error", f"{self.module.name} is not answering."
            self._changed()
            return
        self.before, self.last = first, first
        known = {f.code: f.active for f in first}
        self.phase = "watching"
        self._changed()
        while self.phase == "watching":
            now = self._read()
            if now is None:
                time.sleep(0.3)
                continue
            self.last = now
            self.reads += 1
            step = self.step
            for f in now:
                was = known.get(f.code)
                # New fault, or a stored one that just became active again.
                if (was is None or (was is False and f.active)) and all(h.fault.code != f.code for h in self.hits):
                    self.hits.append(Hit(f, step, time.time()))
                known[f.code] = f.active
            self._changed()
            time.sleep(0.7)
        self._changed()
