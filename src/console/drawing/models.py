"""Immutable models shared by the drawing loader and offline planner."""

from dataclasses import dataclass


class DrawingError(ValueError):
    """A stable, pre-I/O drawing import or planning rejection."""


@dataclass(frozen=True)
class Canvas:
    width: float
    height: float
    source_width: int
    source_height: int
    source_aspect_ratio: float
    target_width_mm: float
    target_height_mm: float


@dataclass(frozen=True)
class Stroke:
    id: str
    order: int
    points: tuple
    closed: bool


@dataclass(frozen=True)
class ColorGroup:
    name: str
    strokes: tuple


@dataclass(frozen=True)
class DrawingJob:
    version: str
    canvas: Canvas
    groups: tuple
    source_shape: str
    canonical_sha256: str

    @property
    def stroke_count(self):
        return sum(len(group.strokes) for group in self.groups)

    @property
    def point_count(self):
        return sum(
            len(stroke.points)
            for group in self.groups
            for stroke in group.strokes
        )


@dataclass(frozen=True)
class PlanCheckpoint:
    group_index: int
    stroke_index: int
    next_point_index: int

    def to_dict(self):
        return {
            "group_index": self.group_index,
            "stroke_index": self.stroke_index,
            "next_point_index": self.next_point_index,
        }


@dataclass(frozen=True)
class PlanStep:
    kind: str
    label: str
    payload: dict

    def to_dict(self):
        return {
            "kind": self.kind,
            "label": self.label,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class DrawingPlan:
    job_sha256: str
    config_sha256: str
    json_axis_offset_mm: float
    steps: tuple
    complete: bool
    next_checkpoint: object
    statistics: dict

    def to_dict(self, include_steps=True):
        result = {
            "job_sha256": self.job_sha256,
            "config_sha256": self.config_sha256,
            "json_axis_offset_mm": self.json_axis_offset_mm,
            "complete": self.complete,
            "next_checkpoint": (
                None
                if self.next_checkpoint is None
                else self.next_checkpoint.to_dict()
            ),
            "statistics": dict(self.statistics),
        }
        if include_steps:
            result["steps"] = [step.to_dict() for step in self.steps]
        return result
