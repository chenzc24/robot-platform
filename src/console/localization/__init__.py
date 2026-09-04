"""PC localization locking and future coordinated-task context."""

from .geometry import GeometryError, RobotGeometry, average_transforms, compose, inverse, load_robot_geometry, rigid_transform
from .state_machine import LocalizationLockStateMachine, LocalizationStateError


def create_localization_state_machine(config, clock=None):
    localization = config.localization
    if not localization.enabled:
        return LocalizationLockStateMachine(enabled=False, clock=clock)
    geometry = None
    error = None
    if not localization.complete:
        error = "localization_configuration_incomplete"
    elif not config.vision.enabled or not config.vision.complete:
        error = "localization_requires_vision"
    else:
        try:
            geometry = load_robot_geometry(localization.geometry_path)
        except GeometryError as caught:
            error = str(caught)
    return LocalizationLockStateMachine(
        enabled=True,
        geometry=geometry,
        configuration_error=error,
        settle_time_ms=localization.settle_time_ms,
        sample_window_ms=localization.sample_window_ms,
        min_valid_samples=localization.min_valid_samples,
        min_visible_tags=localization.min_visible_tags,
        max_translation_spread_mm=localization.max_translation_spread_mm,
        max_rotation_spread_deg=localization.max_rotation_spread_deg,
        clock=clock,
    )


__all__ = [
    "GeometryError",
    "LocalizationLockStateMachine",
    "LocalizationStateError",
    "RobotGeometry",
    "average_transforms",
    "compose",
    "create_localization_state_machine",
    "inverse",
    "load_robot_geometry",
    "rigid_transform",
]
