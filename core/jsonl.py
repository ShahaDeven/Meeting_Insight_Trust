"""JSONL in/out: the contract between stages, so any stage can be replaced."""

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)


def write_jsonl(path: Path, rows: Iterable[BaseModel | dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            data = row.model_dump(mode="json") if isinstance(row, BaseModel) else row
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: Path, model: type[M] | None = None) -> Iterator[M | dict]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                yield model.model_validate(data) if model else data
