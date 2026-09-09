"""Pure tests for grouped drawing validation, geometry, and checkpoints."""

import copy
import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "console"))

from drawing.config import parse_drawing_config
from drawing.loader import canonical_document, parse_drawing_document
from drawing.models import DrawingError, PlanCheckpoint
from drawing.planner import build_drawing_plan


def canvas():
    return {
        "width": 1,
        "height": 1,
        "source_width": 100,
        "source_height": 100,
        "source_aspect_ratio": 1,
        "target_width_mm": 210,
        "target_height_mm": 210,
    }


def stroke(stroke_id="s1", order=1, points=None):
    return {
        "id": stroke_id,
        "order": order,
        "points": points or [[0, 0.25], [0.5, 0.5], [1, 0.75]],
        "closed": False,
    }


def grouped_document():
    return {
        "version": "1.0",
        "coordinate_space": "normalized",
        "axis": {
            "origin": "top-left",
            "x_positive": "right",
            "y_positive": "down",
        },
        "canvas": canvas(),
        "groups": [
            {"name": "red", "strokes": [stroke()]},
            {
                "name": "blue",
                "strokes": [stroke("s2", 2, [[0.2, 0.2], [0.3, 0.3]])],
            },
        ],
    }


def config_document(**geometry_overrides):
    geometry = {
        "canvas_width_mm": 100,
        "canvas_height_mm": 80,
        "user_y_offset_mm": -50,
        "user_z_offset_mm": -40,
        "home_pose_user_y_mm": 0,
        "reachable_user_y_min_mm": -60,
        "reachable_user_y_max_mm": 60,
        "pen_travel_x_mm": 20,
        "home_joints_deg": [-120, 0, -90, -90, -30, 90],
        "user": 0,
        "tool": 0,
        "draw_speed_pct": 12,
        "draw_blend_pct": 100,
        "travel_speed_pct": 50,
        "accel_pct": 20,
    }
    geometry.update(geometry_overrides)
    return {
        "production_ready": False,
        "flat_group_name": "default",
        "group_pen_slots": {"default": "P1", "red": "P1", "blue": "P2"},
        "pen_rack": {
            "change_depth_mm": 60,
            "final_return_depth_mm": 30,
            "gripper_open_mm": 60,
            "gripper_closed_mm": 1,
            "slots": {
                "P1": {"joint_deg": [1, 2, 3, 4, 5, 6]},
                "P2": {"joint_deg": [2, 3, 4, 5, 6, 7]},
                "P3": {"joint_deg": [3, 4, 5, 6, 7, 8]},
                "P4": {"joint_deg": [4, 5, 6, 7, 8, 9]},
            },
        },
        "geometry": geometry,
    }


class DrawingLoaderTests(unittest.TestCase):
    def test_grouped_and_flat_shapes_normalize_deterministically(self):
        grouped = grouped_document()
        grouped["groups"][0]["strokes"] = [
            stroke("later", 2),
            stroke("earlier", 1),
        ]
        job = parse_drawing_document(grouped)
        self.assertEqual(job.source_shape, "grouped")
        self.assertEqual([item.id for item in job.groups[0].strokes], ["earlier", "later"])
        self.assertEqual(job.stroke_count, 3)
        self.assertEqual(job.point_count, 8)

        flat = {key: value for key, value in grouped.items() if key != "groups"}
        flat["strokes"] = [stroke()]
        flat_job = parse_drawing_document(flat, flat_group_name="ink")
        self.assertEqual(flat_job.source_shape, "flat")
        self.assertEqual(flat_job.groups[0].name, "ink")
        self.assertEqual(flat_job.canonical_sha256, parse_drawing_document(flat, "ink").canonical_sha256)

    def test_canonical_output_is_grouped_and_json_serializable(self):
        job = parse_drawing_document(grouped_document())
        output = canonical_document(job)
        self.assertIn("groups", output)
        self.assertNotIn("strokes", output)
        json.dumps(output, ensure_ascii=False)

    def test_rejects_unknown_fields_bad_axes_points_and_duplicate_ids(self):
        cases = []
        extra = grouped_document()
        extra["unexpected"] = True
        cases.append(extra)
        bad_axis = grouped_document()
        bad_axis["axis"]["y_positive"] = "up"
        cases.append(bad_axis)
        bad_point = grouped_document()
        bad_point["groups"][0]["strokes"][0]["points"][0] = [1.1, 0]
        cases.append(bad_point)
        duplicate = grouped_document()
        duplicate["groups"][1]["strokes"][0]["id"] = "s1"
        cases.append(duplicate)
        for document in cases:
            with self.subTest(document=document), self.assertRaises(DrawingError):
                parse_drawing_document(document)


class DrawingConfigTests(unittest.TestCase):
    def test_requires_complete_geometry_and_explicit_nonempty_pen_slots(self):
        config = parse_drawing_config(config_document())
        self.assertEqual(config.pen_slot("red").name, "P1")
        self.assertFalse(config.production_ready)
        for mutation in (
            "missing",
            "blank",
            "range",
            "speed",
            "blend",
            "travel",
            "accel",
        ):
            document = config_document()
            if mutation == "missing":
                del document["geometry"]["home_pose_user_y_mm"]
            elif mutation == "blank":
                document["group_pen_slots"]["red"] = ""
            elif mutation == "range":
                document["geometry"]["reachable_user_y_min_mm"] = 60
            elif mutation == "speed":
                document["geometry"]["draw_speed_pct"] = 101
            elif mutation == "blend":
                document["geometry"]["draw_blend_pct"] = 101
            elif mutation == "travel":
                document["geometry"]["travel_speed_pct"] = 0
            else:
                document["geometry"]["accel_pct"] = "default"
            with self.subTest(mutation=mutation), self.assertRaises(DrawingError):
                parse_drawing_config(document)

    def test_requires_exactly_four_slots_and_known_group_mappings(self):
        document = config_document()
        del document["group_pen_slots"]["default"]
        del document["pen_rack"]["slots"]["P4"]
        with self.assertRaisesRegex(DrawingError, "exactly P1, P2, P3 and P4"):
            parse_drawing_config(document)

        document = config_document()
        document["group_pen_slots"]["red"] = "P5"
        with self.assertRaisesRegex(DrawingError, "must be one of P1..P4"):
            parse_drawing_config(document)


class DrawingPlannerTests(unittest.TestCase):
    def setUp(self):
        self.job = parse_drawing_document(grouped_document())
        self.config = parse_drawing_config(config_document())

    def test_geometry_matches_explicit_user_yz_mapping_and_counts(self):
        plan = build_drawing_plan(self.job, self.config)
        self.assertTrue(plan.complete)
        self.assertEqual(plan.statistics["planned_strokes"], 2)
        self.assertEqual(plan.statistics["planned_points"], 5)
        self.assertEqual(plan.statistics["arm_commands"], 4)
        self.assertEqual(plan.statistics["pen_changes"], 2)
        self.assertEqual(plan.statistics["job_bounds"]["relative_user_y_mm"], [-50.0, 50.0])
        self.assertEqual(plan.statistics["job_bounds"]["relative_user_z_mm"], [-20.0, 24.0])
        strokes = [step for step in plan.steps if step.kind == "arm.stroke"]
        self.assertEqual(strokes[0].payload["anchor_translation_mm"], [0.0, -50.0, 20.0])
        self.assertEqual(strokes[0].payload["pen_down_translation_mm"], [-20.0, 0.0, 0.0])
        self.assertEqual(strokes[0].payload["segments_mm"], [[0.0, 50.0, -20.0], [0.0, 50.0, -20.0]])
        self.assertEqual(strokes[0].payload["pen_up_translation_mm"], [20.0, 0.0, 0.0])
        self.assertEqual(strokes[0].payload["draw_speed_pct"], 12)
        self.assertEqual(strokes[0].payload["draw_blend_pct"], 100)
        self.assertEqual(strokes[0].payload["accel_pct"], 20)
        self.assertEqual(strokes[0].payload["travel_speed_pct"], 50)
        pen_steps = [step for step in plan.steps if step.kind.startswith("pen.")]
        self.assertEqual(
            [step.kind for step in pen_steps],
            ["pen.select", "pen.return", "pen.select", "pen.return"],
        )
        self.assertEqual(pen_steps[0].payload["slot"], "P1")
        self.assertEqual(pen_steps[0].payload["steps"][0]["joint_deg"], [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        self.assertEqual(pen_steps[1].payload["depth_mm"], 60.0)
        self.assertEqual(pen_steps[-1].payload["depth_mm"], 30.0)
        self.assertEqual(pen_steps[-1].payload["purpose"], "final_return")

    def test_adjacent_groups_mapped_to_same_slot_do_not_change_pen(self):
        document = config_document()
        document["group_pen_slots"]["blue"] = "P1"
        config = parse_drawing_config(document)
        plan = build_drawing_plan(self.job, config)
        pen_steps = [step for step in plan.steps if step.kind.startswith("pen.")]
        self.assertEqual([step.kind for step in pen_steps], ["pen.select", "pen.return"])
        self.assertEqual(plan.statistics["pen_changes"], 1)

    def test_json_axis_offset_changes_anchor_not_segment_delta(self):
        plan = build_drawing_plan(self.job, self.config, json_axis_offset_mm=10)
        stroke_step = next(step for step in plan.steps if step.kind == "arm.stroke")
        self.assertEqual(stroke_step.payload["anchor_translation_mm"][1], -40.0)
        self.assertEqual(stroke_step.payload["segments_mm"][0][1], 50.0)

    def test_first_point_outside_range_homes_before_reposition_barrier(self):
        config = parse_drawing_config(
            config_document(home_pose_user_y_mm=200)
        )
        plan = build_drawing_plan(self.job, config)
        self.assertFalse(plan.complete)
        self.assertEqual([step.kind for step in plan.steps], [
            "arm.home", "reposition.required",
        ])
        self.assertEqual(plan.steps[0].payload["purpose"], "reposition_safe_pose")
        self.assertEqual(plan.next_checkpoint, PlanCheckpoint(0, 0, 0))

    def test_midstroke_barrier_lifts_homes_and_resumes_from_anchor(self):
        config = parse_drawing_config(
            config_document(
                reachable_user_y_min_mm=-60,
                reachable_user_y_max_mm=40,
            )
        )
        plan = build_drawing_plan(self.job, config)
        self.assertFalse(plan.complete)
        self.assertEqual(plan.next_checkpoint, PlanCheckpoint(0, 0, 2))
        self.assertEqual(plan.steps[-1].kind, "reposition.required")
        self.assertEqual(plan.steps[-2].payload["purpose"], "reposition_safe_pose")
        self.assertTrue(any(
            step.kind == "pen.return" and step.payload["purpose"] == "group_change_return"
            for step in plan.steps
        ))
        barrier = plan.steps[-1].payload
        self.assertEqual(barrier["required_json_axis_offset_delta_range_mm"], [-60.0, -10.0])
        self.assertEqual(barrier["suggested_json_axis_offset_delta_mm"], -35.0)

        resumed = build_drawing_plan(
            self.job,
            config,
            json_axis_offset_mm=-10,
            checkpoint=plan.next_checkpoint,
        )
        first_stroke = next(step for step in resumed.steps if step.kind == "arm.stroke")
        self.assertIn("queued points 1", first_stroke.label)
        self.assertEqual(first_stroke.payload["anchor_translation_mm"][1], -10.0)

    def test_same_pen_strokes_continue_from_lift_position_without_home(self):
        document = grouped_document()
        document["groups"] = [{
            "name": "red",
            "strokes": [
                stroke("s1", 1, [[0, 0.25], [0.5, 0.5]]),
                stroke("s2", 2, [[0.25, 0.5], [0.5, 0.75]]),
            ],
        }]
        job = parse_drawing_document(document)
        plan = build_drawing_plan(job, self.config)
        homes = [step for step in plan.steps if step.kind == "arm.home"]
        strokes = [step for step in plan.steps if step.kind == "arm.stroke"]
        self.assertEqual(len(homes), 1)
        self.assertEqual(len(strokes), 2)
        self.assertEqual(strokes[1].payload["anchor_translation_mm"], [0.0, -25.0, 0.0])

    def test_segment_wider_than_range_is_rejected(self):
        document = grouped_document()
        document["groups"] = [
            {
                "name": "red",
                "strokes": [stroke("wide", 1, [[0, 0.25], [1, 0.75]])],
            }
        ]
        job = parse_drawing_document(document)
        config = parse_drawing_config(
            config_document(
                reachable_user_y_min_mm=-60,
                reachable_user_y_max_mm=20,
            )
        )
        with self.assertRaisesRegex(DrawingError, "segment is wider"):
            build_drawing_plan(job, config)

    def test_missing_group_mapping_rejects_before_plan(self):
        document = config_document()
        del document["group_pen_slots"]["blue"]
        config = parse_drawing_config(document)
        with self.assertRaisesRegex(DrawingError, "no pen-slot mapping"):
            build_drawing_plan(self.job, config)


if __name__ == "__main__":
    unittest.main()
