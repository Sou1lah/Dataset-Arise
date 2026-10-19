import tempfile
import unittest
from pathlib import Path

import pandas as pd

from dataset_cleaner.cleaner import Cleaner
from dataset_cleaner.data import save_dataset
from dataset_cleaner.reporter import generate_report
from dataset_cleaner.scanner import scan_directory


class CleanerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original = pd.DataFrame({
            "age": [10.0, None, 30.0, 30.0],
            "group": ["a", "b", "b", "b"],
        })
        self.cleaner = Cleaner(self.original)

    def test_cleaning_never_mutates_source_and_undo_restores_working_copy(self) -> None:
        self.cleaner.fill_nulls("mean")
        self.assertTrue(self.original["age"].isna().iloc[1])
        self.assertFalse(self.cleaner.working["age"].isna().any())
        self.cleaner.undo()
        self.assertTrue(self.cleaner.working["age"].isna().iloc[1])

    def test_cleaning_copy_can_save_without_overwriting_original(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "sample.csv"
            output = Path(temp) / "cleaned" / "sample_cleaned_v1.csv"
            self.original.to_csv(source, index=False)
            save_dataset(self.cleaner.working, output)
            pd.testing.assert_frame_equal(pd.read_csv(source), self.original)
            self.assertTrue(output.exists())
            with self.assertRaises(FileExistsError):
                save_dataset(self.cleaner.working, output)

    def test_scan_and_ansi_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "sample.csv").write_text("x\n1\n", encoding="utf-8")
            (root / "ignore.txt").write_text("not a dataset", encoding="utf-8")
            self.assertEqual([item.name for item in scan_directory(root)], ["sample.csv"])
            report = generate_report(
                root / "sample.csv",
                self.original,
                self.cleaner.working,
                self.cleaner.history,
                root / "reports",
            )
            self.assertTrue(report.exists())
            self.assertIn("\x1b[", report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
