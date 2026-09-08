from PIL import Image

import app.detectors.registry as registry_module
from app.detectors import UnknownDetectorError, build_detector_registry


def test_builtin_detectors_are_lazy_and_ordered() -> None:
    registry = build_detector_registry("")
    assert registry.ids() == ["lineart", "pidinet", "hed"]
    assert all(not detector.loaded for detector in registry.values())


def test_external_detector_loads_without_editing_api_routes() -> None:
    registry = build_detector_registry("examples.custom_detector:create_detector")
    assert registry.ids()[-1] == "partner_edge"
    assert registry.get("partner_edge").metadata.repository == "local-plugin"
    output = registry.get("partner_edge").predict(Image.new("RGB", (32, 32), "white"), 256)
    assert output.mode == "L"


def test_unknown_detector_error_lists_available_ids() -> None:
    registry = build_detector_registry("")
    try:
        registry.get("missing")
    except UnknownDetectorError as exc:
        assert "lineart" in str(exc)
    else:
        raise AssertionError("Unknown detector should fail")


def test_complete_bundled_weights_are_used_without_environment(monkeypatch, tmp_path) -> None:
    bundled = tmp_path / "models"
    bundled.mkdir()
    for filename in registry_module.REQUIRED_MODEL_FILES:
        (bundled / filename).write_bytes(b"test")
    monkeypatch.delenv("LINEART_MODEL_REPOSITORY", raising=False)
    monkeypatch.setattr(registry_module, "BUNDLED_MODEL_DIRECTORY", bundled)

    assert registry_module.resolve_model_repository() == str(bundled)


def test_incomplete_bundled_weights_fall_back_to_remote(monkeypatch, tmp_path) -> None:
    bundled = tmp_path / "models"
    bundled.mkdir()
    (bundled / registry_module.REQUIRED_MODEL_FILES[0]).write_bytes(b"test")
    monkeypatch.delenv("LINEART_MODEL_REPOSITORY", raising=False)
    monkeypatch.setattr(registry_module, "BUNDLED_MODEL_DIRECTORY", bundled)

    assert registry_module.resolve_model_repository() == registry_module.DEFAULT_MODEL_REPOSITORY
