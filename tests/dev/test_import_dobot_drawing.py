"""Tests for literal-only Dobot var.py conversion."""

import importlib.util
import json
import pathlib
import tempfile
import unittest
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "import_dobot_drawing", ROOT / "tools/dev/import_dobot_drawing.py"
)
IMPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORTER)


def document():
    return {
        "version": "1.0",
        "coordinate_space": "normalized",
        "axis": {"origin": "top-left", "x_positive": "right", "y_positive": "down"},
        "canvas": {
            "width": 1,
            "height": 1,
            "source_width": 10,
            "source_height": 10,
            "source_aspect_ratio": 1,
            "target_width_mm": 10,
            "target_height_mm": 10,
        },
        "groups": [
            {
                "name": "black",
                "strokes": [
                    {
                        "id": "s1",
                        "order": 1,
                        "points": [[0, 0], [1, 1]],
                        "closed": False,
                    }
                ],
            }
        ],
    }


class DobotImporterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_zip_literal_converts_to_canonical_grouped_json(self):
        archive = self.root / "project.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("project/var.py", "data = " + repr(document()))
        target = self.root / "drawing.json"
        result = IMPORTER.import_dobot_drawing(archive, target)
        converted = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual((result["groups"], result["strokes"], result["points"]), (1, 1, 2))
        self.assertEqual(converted["groups"][0]["name"], "black")
        self.assertEqual(len(result["canonical_sha256"]), 64)

    def test_nonliteral_source_is_rejected_without_execution(self):
        marker = self.root / "executed.txt"
        source = "data = __import__('pathlib').Path(%r).write_text('bad')" % str(marker)
        with self.assertRaisesRegex(IMPORTER.DrawingError, "literals only"):
            IMPORTER.parse_var_literal(source)
        self.assertFalse(marker.exists())

    def test_extra_statements_duplicate_var_and_overwrite_are_rejected(self):
        with self.assertRaisesRegex(IMPORTER.DrawingError, "exactly one"):
            IMPORTER.parse_var_literal("data = {}\nother = 1\n")
        archive = self.root / "duplicate.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("a/var.py", "data = {}")
            output.writestr("b/var.py", "data = {}")
        with self.assertRaisesRegex(IMPORTER.DrawingError, "exactly one"):
            IMPORTER.import_dobot_drawing(archive, self.root / "out.json")

        project = self.root / "project"
        project.mkdir()
        (project / "var.py").write_text("data = " + repr(document()), encoding="utf-8")
        target = self.root / "existing.json"
        target.write_text("preserve", encoding="utf-8")
        with self.assertRaisesRegex(IMPORTER.DrawingError, "already exists"):
            IMPORTER.import_dobot_drawing(project, target)
        self.assertEqual(target.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
