from __future__ import annotations

import os
from pathlib import Path
import tempfile

import pandas as pd


def load_dataset(path: str | Path) -> pd.DataFrame:
    """Read supported tabular data into a fresh in-memory DataFrame."""
    source = Path(path).expanduser().resolve()
    extension = source.suffix.lower()
    readers = {
        ".csv": pd.read_csv,
        ".xlsx": pd.read_excel,
        ".xls": pd.read_excel,
        ".parquet": pd.read_parquet,
        ".json": pd.read_json,
    }
    if extension not in readers:
        raise ValueError(f"Unsupported dataset format: {extension or '(no extension)'}")
    try:
        return readers[extension](source).copy(deep=True)
    except Exception as exc:
        raise ValueError(f"Could not load {source.name}: {exc}") from exc


def save_dataset(frame: pd.DataFrame, path: str | Path) -> Path:
    """Save a cleaned working copy; never writes to the source path."""
    destination = Path(path).expanduser().resolve()
    extension = destination.suffix.lower()
    if extension not in {".csv", ".xlsx", ".parquet", ".json"}:
        raise ValueError(f"Unsupported output format: {extension}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}.",
        suffix=f".tmp{extension}",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    writers = {
        ".csv": lambda: frame.to_csv(temporary, index=False),
        ".xlsx": lambda: frame.to_excel(temporary, index=False, engine="openpyxl"),
        ".parquet": lambda: frame.to_parquet(temporary, index=False),
        ".json": lambda: frame.to_json(temporary, orient="records", indent=2),
    }
    try:
        writers[extension]()
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
