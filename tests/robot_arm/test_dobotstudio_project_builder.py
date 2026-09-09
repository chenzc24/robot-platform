import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
BUILDER_PATH = ROOT / "tools" / "robot_arm" / "build_dobotstudio_project.py"
spec = importlib.util.spec_from_file_location("dobotstudio_project_builder", BUILDER_PATH)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class DobotStudioProjectBuilderTests(unittest.TestCase):
    def test_builds_two_code_files_and_required_project_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / "dobotstudio-project"
            result = builder.build(output)

            self.assertEqual(
                {item.name for item in output.iterdir()},
                {"main.py", "var.py", "prj.json", "point.json"},
            )
            self.assertEqual(tuple(item.name for item in result), ("main.py", "var.py", "prj.json", "point.json"))
            main = (output / "main.py").read_text(encoding="utf-8")
            self.assertNotIn("from arm_motion_service import", main)
            self.assertNotIn("from motion_link import", main)
            self.assertIn("from var import *", main)
            self.assertIn("MOTION_ENABLED = False", (output / "var.py").read_text(encoding="utf-8"))
            self.assertEqual(
                (output / "prj.json").read_text(encoding="utf-8"),
                '{"main":"main.py","teach":"point.json","var":"var.py","submain":[],"type":"Python"}\n',
            )
            self.assertEqual((output / "point.json").read_text(encoding="utf-8"), "[]\n")
            compile(main, str(output / "main.py"), "exec")

    def test_refuses_to_mix_generated_project_with_other_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory)
            (output / "old-project-file.py").write_text("pass\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unexpected_files"):
                builder.build(output)

    def test_yolo_option_enables_repeatable_engineering_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / "dobotstudio-project"
            builder.build(output, yolo=True)
            policy = (output / "var.py").read_text(encoding="utf-8")
            self.assertIn("MOTION_ENABLED = False", policy)
            self.assertIn("YOLO_MODE = True", policy)
            main = (output / "main.py").read_text(encoding="utf-8")
            self.assertIn("RelJointMovJ", main)
            self.assertIn("RelMovLUser", main)
            self.assertIn("STROKE_BEGIN", main)
            self.assertIn("STROKE_EXECUTE", main)


if __name__ == "__main__":
    unittest.main()
