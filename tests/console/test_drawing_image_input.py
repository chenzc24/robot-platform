"""Image artifact and physical drawing-board contract tests."""

import io
import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/console"))

from drawing.config import parse_drawing_config
from drawing.image_input import process_image_to_artifacts, validate_job_canvas
from drawing.loader import parse_drawing_document
from drawing.models import DrawingError


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def drawing_document(width=100, height=80):
    return {
        "version": "1.0", "coordinate_space": "normalized",
        "axis": {"origin": "top-left", "x_positive": "right", "y_positive": "down"},
        "canvas": {"width": 1, "height": 0.8, "source_width": 10,
                   "source_height": 8, "source_aspect_ratio": 1.25,
                   "target_width_mm": width, "target_height_mm": height},
        "strokes": [{"id": "s1", "order": 1, "points": [[0, 0], [1, 0.8]], "closed": False}],
    }


def drawing_config():
    return parse_drawing_config({
        "production_ready": False, "flat_group_name": "default",
        "group_pen_slots": {"default": "P1"},
        "pen_rack": {"change_depth_mm": 60, "final_return_depth_mm": 30,
                     "gripper_open_mm": 60, "gripper_closed_mm": 1,
                     "slots": {name: {"joint_deg": [index] * 6}
                               for index, name in enumerate(("P1", "P2", "P3", "P4"), 1)}},
        "geometry": {"canvas_width_mm": 100, "canvas_height_mm": 80,
                     "user_y_offset_mm": -50, "user_z_offset_mm": -40,
                     "home_pose_user_y_mm": 0, "reachable_user_y_min_mm": -100,
                     "reachable_user_y_max_mm": 100, "pen_travel_x_mm": 51,
                     "home_joints_deg": [-120, 0, -90, -90, -30, 90],
                     "user": 0, "tool": 0, "draw_speed_pct": 12,
                     "draw_blend_pct": 100, "travel_speed_pct": 50, "accel_pct": 20},
    })


class DrawingImageInputTests(unittest.TestCase):
    def test_processes_loopback_image_and_preserves_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = pathlib.Path(folder)
            image = folder / "input.png"
            image.write_bytes(b"image")
            payload = {"strokes_document": drawing_document(), "audit_document": {"warnings": []}}
            requests = []

            def opener(request, timeout):
                requests.append((request, timeout))
                return Response(payload)

            result = process_image_to_artifacts(
                image, folder / "output", 100, 80, opener=opener,
            )
            self.assertEqual(json.loads(result["drawing_path"].read_text()), drawing_document())
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0][0].full_url, "http://127.0.0.1:8000/api/v1/process")
            self.assertIn(b'"target_width_mm": 100.0', requests[0][0].data)
            process_image_to_artifacts(image, folder / "output", 100, 80, opener=opener)

    def test_rejects_non_loopback_service(self):
        with tempfile.TemporaryDirectory() as folder:
            image = pathlib.Path(folder) / "input.png"
            image.write_bytes(b"image")
            with self.assertRaisesRegex(DrawingError, "must_be_loopback"):
                process_image_to_artifacts(
                    image, pathlib.Path(folder) / "out", 100, 80,
                    base_url="http://example.com", opener=lambda *_a, **_k: None,
                )

    def test_validates_exact_physical_board_size_and_reports_origin(self):
        config = drawing_config()
        job = parse_drawing_document(drawing_document(), "default")
        board = validate_job_canvas(job, config)
        self.assertEqual(board["json_origin_user_y_mm"], -50)
        self.assertEqual(board["json_origin_user_z_mm"], 40)
        wrong = parse_drawing_document(drawing_document(120, 80), "default")
        with self.assertRaisesRegex(DrawingError, "drawing_board_size_mismatch"):
            validate_job_canvas(wrong, config)
        uniformly_larger = parse_drawing_document(drawing_document(200, 160), "default")
        scaled = validate_job_canvas(
            uniformly_larger, config, allow_uniform_rescale=True,
        )
        self.assertEqual(scaled["uniform_canvas_scale"], 0.5)
        with self.assertRaisesRegex(DrawingError, "drawing_board_size_mismatch"):
            validate_job_canvas(wrong, config, allow_uniform_rescale=True)


if __name__ == "__main__":
    unittest.main()
