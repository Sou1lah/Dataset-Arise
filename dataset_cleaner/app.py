from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pandas as pd
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    Static,
)

from .cleaner import Cleaner
from .data import load_dataset, save_dataset
from .reporter import generate_report
from .scanner import DatasetFile, scan_directory


class ConfirmActionScreen(ModalScreen[bool]):
    CSS = """
    ConfirmActionScreen {
        align: center middle;
        background: $background 70%;
    }
    #confirm-card {
        width: 64;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }
    #confirm-message { margin: 1 0; }
    #confirm-buttons { height: 3; align-horizontal: right; }
    #confirm-buttons Button { margin-left: 1; }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-card"):
            yield Label("Confirm cleaning action", classes="section-title")
            yield Static(self.message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("Cancel", id="cancel-action")
                yield Button("Apply to working copy", variant="primary", id="confirm-action")

    @on(Button.Pressed, "#confirm-action")
    def confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#cancel-action")
    def cancel(self) -> None:
        self.dismiss(False)


class DatasetAriseApp(App[None]):
    TITLE = "dataset-arise"
    SUB_TITLE = "inspect · clean a copy · report"
    CSS = """
    Screen { background: #11111b; color: #cdd6f4; }
    Header { background: #181825; color: #89b4fa; }
    Footer { background: #181825; }
    .section-title { color: #89b4fa; text-style: bold; margin-bottom: 1; }
    #toolbar { height: 3; margin: 1 1 0 1; }
    #scan-path { width: 1fr; }
    #scan-button { width: 16; margin-left: 1; }
    #status { height: 2; padding: 0 2; color: #a6adc8; }
    #workspace { height: 1fr; margin: 0 1 1 1; }
    #files-panel { width: 34; min-width: 24; border: round #45475a; padding: 1; }
    #dataset-list { height: 1fr; }
    #data-panel { width: 1fr; border: round #45475a; padding: 1; margin-left: 1; }
    #dataset-info { height: 4; color: #a6adc8; }
    #preview-table { height: 1fr; }
    #clean-panel { height: auto; max-height: 15; border: round #45475a; padding: 1; margin: 0 1 1 1; }
    #clean-controls { height: 3; }
    #operation { width: 34; }
    #columns { width: 1fr; margin-left: 1; }
    #apply-action { width: 15; margin-left: 1; }
    #file-actions { height: 3; margin-top: 1; }
    #file-actions Button { margin-right: 1; }
    #tips { height: 2; color: #a6adc8; padding: 0 2; }
    Button { background: #313244; }
    Button:hover { background: #45475a; }
    Button.-primary { background: #1e66f5; }
    ListView > ListItem.--highlight { background: #313244; }
    DataTable > .datatable--header { background: #313244; color: #89b4fa; }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "scan", "Rescan"),
        ("u", "undo", "Undo"),
    ]

    def __init__(self, initial_path: str | Path | None = None) -> None:
        super().__init__()
        self.initial_path = Path(initial_path or Path.cwd()).expanduser()
        self.datasets: list[DatasetFile] = []
        self.source_path: Path | None = None
        self.original: pd.DataFrame | None = None
        self.cleaner: Cleaner | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="toolbar"):
            yield Input(str(self.initial_path), placeholder="Directory containing datasets", id="scan-path")
            yield Button("Scan folder", variant="primary", id="scan-button")
        yield Static("Choose a folder and scan for CSV, Excel, Parquet, or JSON files.", id="status")
        with Horizontal(id="workspace"):
            with Vertical(id="files-panel"):
                yield Label("DATASETS", classes="section-title")
                yield ListView(id="dataset-list")
            with Vertical(id="data-panel"):
                yield Label("PREVIEW", classes="section-title")
                yield Static("Select a dataset to inspect its shape, missing values, and sample rows.", id="dataset-info")
                yield DataTable(id="preview-table", cursor_type="row", zebra_stripes=True)
        with Vertical(id="clean-panel"):
            yield Label("CLEAN WORKING COPY", classes="section-title")
            with Horizontal(id="clean-controls"):
                yield Select(
                    [
                        ("Fill missing values · mean", "fill_mean"),
                        ("Fill missing values · median", "fill_median"),
                        ("Fill missing values · mode", "fill_mode"),
                        ("Drop rows with missing values", "drop_nulls"),
                        ("Drop duplicate rows", "duplicates"),
                        ("Scale numeric columns · standard", "scale_standard"),
                        ("Scale numeric columns · min-max", "scale_minmax"),
                        ("Encode categories · label", "encode_label"),
                        ("Encode categories · one-hot", "encode_onehot"),
                        ("Drop selected columns", "drop_columns"),
                        ("Rename columns", "rename_columns"),
                        ("Reset row index", "reset_index"),
                    ],
                    prompt="Choose a cleaning action",
                    id="operation",
                )
                yield Input(placeholder="Columns: name, age  |  Rename: old -> new", id="columns")
                yield Button("Preview action", variant="primary", id="apply-action")
            with Horizontal(id="file-actions"):
                yield Button("Undo", id="undo-action")
                yield Button("Save cleaned copy", id="save-copy")
                yield Button("Create & open report", id="create-report", variant="success")
                yield Button("Quit", id="quit-button")
        yield Static("Original files are read-only. Cleaning actions affect an in-memory copy.  q quit · r rescan · u undo", id="tips")
        yield Footer()

    def on_mount(self) -> None:
        self.action_scan()

    def action_scan(self) -> None:
        path_input = self.query_one("#scan-path", Input)
        file_list = self.query_one("#dataset-list", ListView)
        file_list.clear()
        self.datasets = []
        try:
            self.datasets = scan_directory(path_input.value)
        except (OSError, ValueError) as exc:
            self._set_status(f"Could not scan folder: {exc}", error=True)
            return
        for dataset in self.datasets:
            entry = Text.assemble(
                (dataset.name, "green"),
                (f"\n{dataset.size_label}", "dim"),
            )
            file_list.append(ListItem(Static(entry)))
        if self.datasets:
            self._set_status(f"Found {len(self.datasets)} dataset(s) in {Path(path_input.value).expanduser().resolve()}. Select one to preview.")
            file_list.focus()
        else:
            self._set_status("No supported data files found in this folder.")
            path_input.focus()

    @on(Button.Pressed, "#scan-button")
    def scan_button(self) -> None:
        self.action_scan()

    @on(ListView.Selected, "#dataset-list")
    def select_dataset(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is None or index >= len(self.datasets):
            return
        source = self.datasets[index].path
        try:
            original = load_dataset(source)
            cleaner = Cleaner(original)
        except (OSError, ValueError, ImportError) as exc:
            self._set_status(f"Could not load {source.name}: {exc}", error=True)
            return
        self.source_path = source
        self.original = original
        self.cleaner = cleaner
        self._render_dataset()
        self._set_status(f"Loaded {source.name}. The source file remains unchanged; edits apply to a working copy.")

    def _render_dataset(self) -> None:
        if self.cleaner is None or self.source_path is None:
            return
        frame = self.cleaner.working
        info = (
            f"[bold]{self.source_path.name}[/bold]   "
            f"{len(frame):,} rows × {len(frame.columns):,} columns   "
            f"{int(frame.isna().sum().sum()):,} missing   "
            f"{int(frame.duplicated().sum()):,} duplicates   "
            f"{frame.memory_usage(index=True, deep=True).sum() / 1024**2:.2f} MiB"
        )
        self.query_one("#dataset-info", Static).update(Text.from_markup(info))
        table = self.query_one("#preview-table", DataTable)
        table.clear(columns=True)
        if frame.shape[1] == 0:
            return
        column_keys = [table.add_column(str(column)) for column in frame.columns]
        rows = []
        for values in frame.head(12).itertuples(index=False, name=None):
            rows.append(tuple(self._display_value(value) for value in values))
        if rows:
            table.add_rows(rows)
        columns_summary = "  ".join(
            f"{column}: {dtype} ({int(frame.iloc[:, index].isna().sum())} null)"
            for index, (column, dtype) in enumerate(zip(frame.columns, frame.dtypes))
        )
        details = Text(info + "\n" + columns_summary)
        details.stylize("dim", len(info) + 1, len(info) + 1 + len(columns_summary))
        self.query_one("#dataset-info", Static).update(details)

    @staticmethod
    def _display_value(value: object) -> str:
        if not pd.api.types.is_scalar(value):
            return str(value)[:100]
        if pd.isna(value):
            return "—"
        return str(value)[:100]

    def _read_action(self, cleaner: Cleaner) -> tuple[str, str]:
        action = self.query_one("#operation", Select).value
        action = str(action)
        field = self.query_one("#columns", Input).value.strip()
        columns = [item.strip() for item in field.split(",") if item.strip()]
        if action == "fill_mean":
            return cleaner.fill_nulls("mean"), ""
        if action == "fill_median":
            return cleaner.fill_nulls("median"), ""
        if action == "fill_mode":
            return cleaner.fill_nulls("mode"), ""
        if action == "drop_nulls":
            return cleaner.drop_null_rows(), ""
        if action == "duplicates":
            return cleaner.drop_duplicates(), ""
        if action == "scale_standard":
            return cleaner.scale_numeric("standard"), ""
        if action == "scale_minmax":
            return cleaner.scale_numeric("minmax"), ""
        if action == "encode_label":
            return cleaner.encode_categoricals(columns, "label"), ""
        if action == "encode_onehot":
            return cleaner.encode_categoricals(columns, "onehot"), ""
        if action == "drop_columns":
            return cleaner.drop_columns(columns), ""
        if action == "rename_columns":
            return cleaner.rename_columns(field), ""
        if action == "reset_index":
            return cleaner.reset_index(), ""
        raise ValueError("Choose a cleaning action.")

    @on(Button.Pressed, "#apply-action")
    def preview_action(self) -> None:
        if self.cleaner is None:
            self._set_status("Select a dataset before cleaning.", error=True)
            return
        try:
            trial = self.cleaner.copy()
            summary, _ = self._read_action(trial)
        except (ValueError, KeyError) as exc:
            self._set_status(str(exc), error=True)
            return
        before = self.cleaner.working
        after = trial.working
        message = (
            f"{summary}\n\n"
            f"Rows: {len(before):,} → {len(after):,}    "
            f"Columns: {len(before.columns):,} → {len(after.columns):,}\n"
            f"Missing cells: {int(before.isna().sum().sum()):,} → {int(after.isna().sum().sum()):,}\n\n"
            "Apply this change to the in-memory working copy? The original file will not be changed."
        )
        self.push_screen(ConfirmActionScreen(message), callback=self._confirm_action)

    def _confirm_action(self, confirmed: bool) -> None:
        if not confirmed or self.cleaner is None:
            self._set_status("Cleaning action cancelled.")
            return
        try:
            summary, _ = self._read_action(self.cleaner)
        except (ValueError, KeyError) as exc:
            self._set_status(str(exc), error=True)
            return
        self._render_dataset()
        self._set_status(summary)

    @on(Button.Pressed, "#undo-action")
    def undo_button(self) -> None:
        self.action_undo()

    @on(Button.Pressed, "#quit-button")
    def quit_button(self) -> None:
        self.exit()

    def action_undo(self) -> None:
        if self.cleaner is None:
            self._set_status("Select a dataset before undoing an action.", error=True)
            return
        self._set_status(self.cleaner.undo())
        self._render_dataset()

    @on(Button.Pressed, "#save-copy")
    def save_copy_button(self) -> None:
        if self.cleaner is None or self.source_path is None:
            self._set_status("Select a dataset before saving.", error=True)
            return
        output_dir = self.source_path.parent / "cleaned"
        extension = self.source_path.suffix.lower()
        if extension == ".xls":
            extension = ".xlsx"
        stem = f"{self.source_path.stem}_cleaned"
        version = 1
        destination = output_dir / f"{stem}_v{version}{extension}"
        while destination.exists():
            version += 1
            destination = output_dir / f"{stem}_v{version}{extension}"
        try:
            saved = save_dataset(self.cleaner.working, destination)
        except (OSError, ValueError, ImportError) as exc:
            self._set_status(f"Could not save cleaned copy: {exc}", error=True)
            return
        self._set_status(f"Saved a new cleaned copy: {saved}")

    @on(Button.Pressed, "#create-report")
    def create_report_button(self) -> None:
        if self.cleaner is None or self.original is None or self.source_path is None:
            self._set_status("Select a dataset before creating a report.", error=True)
            return
        report_dir = Path(__file__).resolve().parents[1] / "reports"
        try:
            report = generate_report(
                self.source_path,
                self.original,
                self.cleaner.working,
                self.cleaner.history,
                report_dir,
            )
        except (OSError, ValueError) as exc:
            self._set_status(f"Could not create report: {exc}", error=True)
            return
        self._set_status(f"Report saved: {report}. Opening it now.")
        pager = shutil.which("less")
        if pager:
            try:
                with self.suspend():
                    subprocess.run([pager, "-R", str(report)], check=False)
                self._set_status(f"Report saved: {report}")
                return
            except OSError as exc:
                self._set_status(f"Report saved, but could not open pager: {exc}", error=True)
                return
        opener = shutil.which("xdg-open")
        if opener:
            try:
                subprocess.Popen([opener, str(report)])
                self._set_status(f"Report saved and opened: {report}")
            except OSError as exc:
                self._set_status(f"Report saved, but could not open it: {exc}", error=True)
        else:
            self._set_status(f"Report saved at {report}; install less or xdg-utils to open it automatically.")

    def _set_status(self, message: str, error: bool = False) -> None:
        label = self.query_one("#status", Static)
        label.update(Text(message, style="bold red" if error else "green"))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Inspect and safely clean tabular datasets.")
    parser.add_argument("directory", nargs="?", type=Path, default=Path.cwd(), help="folder to scan")
    args = parser.parse_args()
    DatasetAriseApp(args.directory).run()
