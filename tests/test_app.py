import tempfile
import unittest
from pathlib import Path

from textual.widgets import ListView

from dataset_cleaner.app import DatasetAriseApp


class AppWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_scan_preview_clean_and_save_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "demo.csv"
            source.write_text("age,group\n10,a\n,b\n30,b\n", encoding="utf-8")
            app = DatasetAriseApp(root)

            async with app.run_test() as pilot:
                await pilot.pause()
                self.assertEqual(len(app.datasets), 1)
                dataset_list = app.query_one("#dataset-list", ListView)
                dataset_list.focus()
                dataset_list.index = 0
                await pilot.press("enter")
                await pilot.pause()
                self.assertEqual(app.source_path, source.resolve())
                self.assertIsNotNone(app.cleaner)

                app.query_one("#operation").value = "drop_nulls"
                await pilot.click("#apply-action")
                await pilot.pause()
                self.assertEqual(app.screen.__class__.__name__, "ConfirmActionScreen")
                await pilot.click("#confirm-action")
                await pilot.pause()
                self.assertEqual(len(app.cleaner.working), 2)

                await pilot.click("#save-copy")
                await pilot.pause()
                self.assertTrue((root / "cleaned" / "demo_cleaned_v1.csv").exists())
                self.assertEqual(source.read_text(encoding="utf-8").count("\n"), 4)


if __name__ == "__main__":
    unittest.main()
