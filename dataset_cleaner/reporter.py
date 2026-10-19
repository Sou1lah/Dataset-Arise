from __future__ import annotations

from datetime import datetime
from io import StringIO
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .cleaner import CleaningStep


def _suggestions(frame: pd.DataFrame) -> list[str]:
    suggestions: list[str] = []
    row_count = len(frame)
    for column, count in frame.isna().sum().items():
        if count:
            percent = count / row_count * 100 if row_count else 0
            suggestions.append(
                f"{column}: still has {count} missing value(s) ({percent:.1f}%). "
                "Consider an appropriate fill strategy or review whether the column is needed."
            )
    for column in frame.select_dtypes(include=["object", "string", "category"]).columns:
        unique = frame[column].nunique(dropna=True)
        if row_count and unique / row_count > 0.5 and unique > 20:
            suggestions.append(
                f"{column}: high cardinality ({unique} distinct values). "
                "Check for identifiers or inconsistent labels before encoding."
            )
    for column in frame.select_dtypes(include="number").columns:
        values = frame[column].dropna()
        if len(values) >= 4:
            q1, q3 = values.quantile([0.25, 0.75])
            spread = q3 - q1
            if spread and ((values < q1 - 1.5 * spread) | (values > q3 + 1.5 * spread)).any():
                suggestions.append(
                    f"{column}: possible outliers detected by the 1.5×IQR rule. "
                    "Review domain context before removing them."
                )
    if not suggestions:
        suggestions.append("No obvious missing-value, high-cardinality, or IQR-outlier issues detected.")
    return suggestions


def generate_report(
    source_path: str | Path,
    original: pd.DataFrame,
    cleaned: pd.DataFrame,
    history: list[CleaningStep],
    reports_dir: str | Path,
) -> Path:
    report_dir = Path(reports_dir).expanduser().resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone()
    stem = Path(source_path).stem
    destination = report_dir / f"report_{stem}_{timestamp:%Y%m%d_%H%M%S}.txt"
    version = 1
    while destination.exists():
        destination = report_dir / f"report_{stem}_{timestamp:%Y%m%d_%H%M%S}_{version}.txt"
        version += 1
    console = Console(
        record=True,
        file=StringIO(),
        force_terminal=True,
        color_system="truecolor",
        width=100,
        no_color=False,
    )
    console.print(Panel.fit(
        f"[bold cyan]DATASET-ARISE[/bold cyan]\n[white]Quality & cleaning report[/white]",
        border_style="cyan",
    ))
    console.print(f"[dim]Dataset:[/dim] {Path(source_path).name}")
    console.print(f"[dim]Generated:[/dim] {timestamp:%Y-%m-%d %H:%M:%S %Z}\n")

    summary = Table(title="Dataset summary", border_style="blue")
    summary.add_column("Measure", style="cyan")
    summary.add_column("Original", justify="right")
    summary.add_column("Working copy", justify="right")
    summary.add_row("Rows", f"{original.shape[0]:,}", f"{cleaned.shape[0]:,}")
    summary.add_row("Columns", f"{original.shape[1]:,}", f"{cleaned.shape[1]:,}")
    summary.add_row("Missing cells", f"{int(original.isna().sum().sum()):,}", f"{int(cleaned.isna().sum().sum()):,}")
    summary.add_row("Duplicate rows", f"{int(original.duplicated().sum()):,}", f"{int(cleaned.duplicated().sum()):,}")
    summary.add_row(
        "Memory",
        f"{original.memory_usage(index=True, deep=True).sum() / 1024**2:.2f} MiB",
        f"{cleaned.memory_usage(index=True, deep=True).sum() / 1024**2:.2f} MiB",
    )
    console.print(summary)

    steps = Table(title="Cleaning history", border_style="green")
    steps.add_column("#", justify="right", style="dim")
    steps.add_column("Action", style="cyan")
    steps.add_column("Details")
    if history:
        for index, item in enumerate(history, 1):
            steps.add_row(str(index), item.name, item.details)
    else:
        steps.add_row("—", "No changes", "The working copy was not modified.")
    console.print(steps)

    nulls = Table(title="Missing values by column", border_style="yellow")
    nulls.add_column("Column", style="cyan")
    nulls.add_column("Before", justify="right")
    nulls.add_column("After", justify="right")
    for column in list(dict.fromkeys([*original.columns, *cleaned.columns])):
        before = int(original[column].isna().sum()) if column in original else 0
        after = int(cleaned[column].isna().sum()) if column in cleaned else 0
        nulls.add_row(str(column), f"{before:,}", f"{after:,}")
    console.print(nulls)

    console.print("\n[bold magenta]Suggestions for improvement[/bold magenta]")
    for suggestion in _suggestions(cleaned):
        console.print(f"  [yellow]•[/yellow] {suggestion}")
    console.print("\n[dim]This report describes data quality, not model or clinical validity.[/dim]")
    destination.write_text(console.export_text(styles=True), encoding="utf-8")
    return destination
