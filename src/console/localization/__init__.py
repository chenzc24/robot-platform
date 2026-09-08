"""PC one-dimensional rail localization and future task context."""

from .state_machine import LocalizationStateError, RailLocalizationStateMachine


def create_localization_state_machine(config, clock=None):
    localization = config.localization
    error = None
    if localization.enabled and (not config.vision.enabled or not config.vision.complete):
        error = "localization_requires_vision"
    return RailLocalizationStateMachine(
        enabled=localization.enabled,
        rail_axis=localization.rail_axis,
        json_axis=localization.json_axis,
        json_origin_rail_position_mm=localization.json_origin_rail_position_mm,
        json_mm_per_rail_mm=localization.json_mm_per_rail_mm,
        configuration_error=error,
        settle_time_ms=localization.settle_time_ms,
        sample_window_ms=localization.sample_window_ms,
        min_valid_samples=localization.min_valid_samples,
        min_visible_tags=localization.min_visible_tags,
        max_position_spread_mm=localization.max_position_spread_mm,
        clock=clock,
    )


__all__ = [
    "LocalizationStateError",
    "RailLocalizationStateMachine",
    "create_localization_state_machine",
]
