from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class CleaningStep:
    name: str
    details: str


class Cleaner:
    """Keep every edit on an undoable working copy, never on the source frame."""

    def __init__(self, original: pd.DataFrame) -> None:
        self.original = original.copy(deep=True)
        self.working = original.copy(deep=True)
        self.history: list[CleaningStep] = []
        self._undo: list[pd.DataFrame] = []

    def copy(self) -> Cleaner:
        duplicate = Cleaner(self.original)
        duplicate.working = self.working.copy(deep=True)
        duplicate.history = list(self.history)
        duplicate._undo = [frame.copy(deep=True) for frame in self._undo]
        return duplicate

    def _change(self, name: str, details: str, operation: Callable[[], None]) -> str:
        before = self.working.copy(deep=True)
        operation()
        if self.working.equals(before) and self.working.columns.equals(before.columns):
            return "No changes were needed."
        self._undo.append(before)
        self.history.append(CleaningStep(name, details))
        return details

    def drop_null_rows(self) -> str:
        removed = int(self.working.isna().any(axis=1).sum())
        if not removed:
            return "No rows contain missing values."
        return self._change(
            "Drop rows with missing values",
            f"Removed {removed} rows containing missing values.",
            lambda: setattr(self, "working", self.working.dropna().copy()),
        )

    def fill_nulls(self, strategy: str) -> str:
        if strategy not in {"mean", "median", "mode"}:
            raise ValueError("Choose mean, median, or mode.")
        filled = 0
        result = self.working.copy(deep=True)
        for column in result.columns:
            missing = int(result[column].isna().sum())
            if not missing:
                continue
            series = result[column]
            if strategy in {"mean", "median"}:
                if not pd.api.types.is_numeric_dtype(series):
                    continue
                value = series.mean() if strategy == "mean" else series.median()
            else:
                modes = series.mode(dropna=True)
                if modes.empty:
                    continue
                value = modes.iloc[0]
            if pd.isna(value):
                continue
            result[column] = series.fillna(value)
            filled += missing
        if not filled:
            return f"No missing values could be filled with {strategy}."
        return self._change(
            f"Fill missing values ({strategy})",
            f"Filled {filled} missing cells using {strategy}.",
            lambda: setattr(self, "working", result),
        )

    def drop_duplicates(self) -> str:
        removed = int(self.working.duplicated().sum())
        if not removed:
            return "No duplicate rows found."
        return self._change(
            "Drop duplicate rows",
            f"Removed {removed} duplicate rows.",
            lambda: setattr(self, "working", self.working.drop_duplicates().copy()),
        )

    def scale_numeric(self, method: str) -> str:
        if method not in {"standard", "minmax"}:
            raise ValueError("Choose standard or minmax scaling.")
        columns = [
            column for column in self.working.select_dtypes(include="number").columns
            if not pd.api.types.is_bool_dtype(self.working[column])
        ]
        if not columns:
            return "No numeric columns to scale."
        result = self.working.copy(deep=True)
        for column in columns:
            values = result[column]
            if method == "standard":
                deviation = values.std(ddof=0)
                result[column] = (values - values.mean()) / deviation if deviation else values.where(values.isna(), 0)
            else:
                minimum, maximum = values.min(), values.max()
                spread = maximum - minimum
                result[column] = (values - minimum) / spread if spread else values.where(values.isna(), 0)
        return self._change(
            f"Scale numeric columns ({method})",
            f"Scaled {len(columns)} numeric columns using {method} scaling.",
            lambda: setattr(self, "working", result),
        )

    def encode_categoricals(self, columns: list[str], method: str) -> str:
        if method not in {"label", "onehot"}:
            raise ValueError("Choose label or onehot encoding.")
        missing = [column for column in columns if column not in self.working.columns]
        if missing:
            raise ValueError(f"Unknown column(s): {', '.join(missing)}")
        if not columns:
            return "Enter at least one categorical column name."
        result = self.working.copy(deep=True)
        categorical = [
            column for column in columns
            if pd.api.types.is_object_dtype(result[column])
            or isinstance(result[column].dtype, pd.CategoricalDtype)
            or pd.api.types.is_string_dtype(result[column])
        ]
        if not categorical:
            return "None of the selected columns are categorical."
        if method == "label":
            for column in categorical:
                codes = pd.Categorical(result[column]).codes
                result[column] = pd.Series(codes, index=result.index).mask(codes == -1, pd.NA).astype("Int64")
        else:
            result = pd.get_dummies(result, columns=categorical, dummy_na=False, dtype=int)
        return self._change(
            f"Encode categorical columns ({method})",
            f"Encoded {len(categorical)} column(s): {', '.join(categorical)}.",
            lambda: setattr(self, "working", result),
        )

    def drop_columns(self, columns: list[str]) -> str:
        if not columns:
            return "Enter one or more column names."
        unknown = [column for column in columns if column not in self.working.columns]
        if unknown:
            raise ValueError(f"Unknown column(s): {', '.join(unknown)}")
        if len(columns) >= len(self.working.columns):
            raise ValueError("Cannot drop every column.")
        return self._change(
            "Drop columns",
            f"Dropped {len(columns)} column(s): {', '.join(columns)}.",
            lambda: setattr(self, "working", self.working.drop(columns=columns).copy()),
        )

    def rename_columns(self, mapping_text: str) -> str:
        mapping = {}
        for pair in mapping_text.split(","):
            if not pair.strip():
                continue
            if "->" not in pair:
                raise ValueError("Use old_name -> new_name, one mapping per comma.")
            old, new = (value.strip() for value in pair.split("->", 1))
            if not old or not new:
                raise ValueError("Column names cannot be empty.")
            mapping[old] = new
        if not mapping:
            return "Enter at least one column rename."
        unknown = [column for column in mapping if column not in self.working.columns]
        if unknown:
            raise ValueError(f"Unknown column(s): {', '.join(unknown)}")
        renamed = self.working.rename(columns=mapping)
        if not renamed.columns.is_unique:
            raise ValueError("The rename would create duplicate column names.")
        return self._change(
            "Rename columns",
            f"Renamed {len(mapping)} column(s).",
            lambda: setattr(self, "working", renamed),
        )

    def reset_index(self) -> str:
        return self._change(
            "Reset index",
            "Reset the working copy's row index.",
            lambda: setattr(self, "working", self.working.reset_index(drop=True)),
        )

    def undo(self) -> str:
        if not self._undo:
            return "There are no cleaning actions to undo."
        self.working = self._undo.pop()
        step = self.history.pop()
        return f"Undid: {step.name}."
