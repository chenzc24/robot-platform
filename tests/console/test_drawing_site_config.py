"""L1 contract tests for the single drawing-site configuration."""

import copy
import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "console"))

from drawing import DrawingError, parse_drawing_site_config
from runtime_config import load_runtime_config


def example_document():
    return json.loads(
        (ROOT / "config" / "drawing.example.json").read_text(encoding="utf-8")
    )


class DrawingSiteConfigTests(unittest.TestCase):
    def test_example_is_one_source_for_all_rail_consumers(self):
        site = parse_drawing_site_config(example_document())
        self.assertEqual(site.drawing.geometry.canvas_width_mm, 700.0)
        self.assertEqual(site.drawing.geometry.canvas_height_mm, 200.0)
        self.assertEqual(site.image_to_json.fit_mode, "contain")
        self.assertEqual(site.image_to_json.short_edge_margin_mm, 10.0)
        self.assertEqual(site.rail.json_mm_per_rail_mm, -1.0)
        self.assertEqual(
            site.control.json_mm_per_rail_mm,
            site.localization.json_mm_per_rail_mm,
        )
        self.assertEqual(
            site.rail.json_origin_rail_position_mm,
            site.localization.json_origin_rail_position_mm,
        )
        self.assertEqual(site.apriltag_board.frame, "drawing_board")

    def test_site_overrides_only_physical_runtime_sections(self):
        site = parse_drawing_site_config(example_document())
        runtime = load_runtime_config(ROOT / "config" / "console.example.json")
        merged = site.apply_runtime(runtime)
        self.assertIs(merged.chassis, runtime.chassis)
        self.assertIs(merged.arm, runtime.arm)
        self.assertIs(merged.video, runtime.video)
        self.assertIs(merged.vision.board_layout, site.apriltag_board)
        self.assertIs(merged.vision.camera_calibration, site.camera_calibration)

    def test_localized_start_requires_the_standard_r0_position(self):
        raw = example_document()
        raw["rail"]["json_origin_rail_position_mm"] = 320.0
        raw["rail"]["start_tolerance_mm"] = 3.0
        site = parse_drawing_site_config(raw)
        self.assertAlmostEqual(
            site.require_standard_start({"rail_position_mm": 322.5}), 2.5
        )
        with self.assertRaisesRegex(DrawingError, "drawing_start_outside_tolerance"):
            site.require_standard_start({"rail_position_mm": 323.1})

    def test_physical_start_is_not_assumed_to_equal_apriltag_r0(self):
        raw = example_document()
        raw["rail"]["physical_start_mm"] = 0.0
        raw["rail"]["json_origin_rail_position_mm"] = 327.4
        site = parse_drawing_site_config(raw)
        self.assertEqual(site.rail.physical_start_mm, 0.0)
        self.assertEqual(site.rail.json_origin_rail_position_mm, 327.4)

    def test_center_delta_reference_is_the_localization_readiness_gate(self):
        raw = example_document()
        raw["localization"].update({
            "enabled": True,
            "method": "center_delta",
            "center_reference": {
                "production_ready": True,
                "reference_id": "zero-v1",
                "image_width": 1280,
                "image_height": 720,
                "tag_centers_px": {
                    "0": [100, 100], "1": [100, 600],
                    "2": [1100, 600], "3": [1100, 100],
                },
                "max_tag_disagreement_mm": 15,
                "max_cross_axis_error_mm": 15,
            },
        })
        raw["vision"]["enabled"] = True
        site = parse_drawing_site_config(raw)
        self.assertEqual(site.localization.method, "center_delta")
        self.assertTrue(site.localization.complete)
        self.assertEqual(site.localization.center_reference.reference_id, "zero-v1")

    def test_margin_and_localization_fail_closed(self):
        cases = []
        margin = example_document()
        margin["image_to_json"]["short_edge_margin_mm"] = 100.0
        cases.append(margin)
        missing = example_document()
        del missing["rail"]["start_tolerance_mm"]
        cases.append(missing)
        no_vision = example_document()
        no_vision["localization"]["enabled"] = True
        no_vision["vision"]["enabled"] = False
        cases.append(no_vision)
        fractional_count = example_document()
        fractional_count["localization"]["min_valid_samples"] = 2.5
        cases.append(fractional_count)
        for document in cases:
            with self.subTest(document=copy.deepcopy(document)):
                with self.assertRaises(DrawingError):
                    parse_drawing_site_config(document)


if __name__ == "__main__":
    unittest.main()
