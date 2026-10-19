from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".parquet", ".json"}


@dataclass(frozen=True)
class DatasetFile:
    path: Path
    size_bytes: int

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def size_label(self) -> str:
        size = float(self.size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"


def scan_directory(directory: str | Path) -> list[DatasetFile]:
    """List supported dataset files directly inside a directory."""
    root = Path(directory).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    datasets = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            try:
                datasets.append(DatasetFile(path=path, size_bytes=path.stat().st_size))
            except OSError as exc:
                raise OSError(f"Could not read file metadata for {path}: {exc}") from exc
    return datasets
