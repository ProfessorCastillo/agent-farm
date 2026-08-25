from __future__ import annotations

import json
import random
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Reservation:
    run_id: str
    model: str
    pool_version: int
    epoch: int
    epoch_seed: int
    epoch_position: int


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


class SchedulerState:
    def __init__(self, path: Path, pool_version: int, models: tuple[str, ...]) -> None:
        self.path = path
        self.pool_version = pool_version
        self.models = models
        self.data = self._load()

    def _new_epoch(self, epoch: int) -> dict[str, Any]:
        seed = secrets.randbits(64)
        order = list(self.models)
        random.Random(seed).shuffle(order)
        return {
            "schema_version": 1,
            "pool_version": self.pool_version,
            "models": list(self.models),
            "epoch": epoch,
            "epoch_seed": seed,
            "order": order,
            "position": 0,
            "inflight": None,
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._new_epoch(1)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1:
            raise ValueError("unsupported scheduler state")
        old_pool = tuple(data.get("models", []))
        if data.get("pool_version") != self.pool_version or old_pool != self.models:
            if data.get("inflight") or data.get("position", 0) < len(data.get("order", [])):
                raise ValueError("model pool changed before the current epoch completed")
            return self._new_epoch(int(data.get("epoch", 0)) + 1)
        return data

    def reserve(self, run_id: str) -> Reservation:
        inflight = self.data.get("inflight")
        if inflight:
            if inflight["run_id"] != run_id:
                raise RuntimeError(f"unfinished run already reserved: {inflight['run_id']}")
            return Reservation(**inflight)

        if self.data["position"] >= len(self.data["order"]):
            self.data = self._new_epoch(int(self.data["epoch"]) + 1)

        position = int(self.data["position"])
        reservation = Reservation(
            run_id=run_id,
            model=str(self.data["order"][position]),
            pool_version=self.pool_version,
            epoch=int(self.data["epoch"]),
            epoch_seed=int(self.data["epoch_seed"]),
            epoch_position=position,
        )
        self.data["inflight"] = asdict(reservation)
        atomic_write_json(self.path, self.data)
        return reservation

    def inflight(self) -> Reservation | None:
        value = self.data.get("inflight")
        return Reservation(**value) if value else None

    def complete(self, run_id: str) -> None:
        inflight = self.data.get("inflight")
        if not inflight or inflight.get("run_id") != run_id:
            raise RuntimeError(f"run is not reserved: {run_id}")
        self.data["position"] = int(self.data["position"]) + 1
        self.data["inflight"] = None
        atomic_write_json(self.path, self.data)
