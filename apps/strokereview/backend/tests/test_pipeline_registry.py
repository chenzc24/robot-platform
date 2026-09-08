from __future__ import annotations

import asyncio
import threading
import time
from io import BytesIO

import pytest
from PIL import Image

from app.models import ProcessingParameters
from app.pipelines import PipelineRequest, UnknownPipelineError, build_pipeline_registry
from app.pipelines.builtins import ClassicPipeline


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (100, 50), "white").save(output, "PNG")
    return output.getvalue()


def request(provider: str) -> PipelineRequest:
    return PipelineRequest(
        content=png_bytes(),
        filename="sample.png",
        content_type="image/png",
        input_kind="raster",
        parameters=ProcessingParameters(provider=provider),
    )


def test_builtin_pipeline_order_and_metadata() -> None:
    registry = build_pipeline_registry("")
    assert registry.selectable_ids() == ["classic", "lineart", "pidinet", "hed", "qwen_cloud", "mock"]
    assert registry.get("lineart").metadata.requires_model_service is True
    assert registry.get("qwen_cloud").metadata.is_cloud is True


def test_external_full_pipeline_loads_without_core_route_changes() -> None:
    registry = build_pipeline_registry("examples.custom_pipeline:create_pipeline")
    assert registry.selectable_ids()[-1] == "partner_example"
    response = asyncio.run(registry.process(request("partner_example")))
    assert response.audit_document.processing.actual_provider == "partner_example"
    assert len(response.strokes_document.strokes) == 1
    assert response.audit_document.warnings == ["example_pipeline_output"]


def test_unknown_provider_has_actionable_error() -> None:
    registry = build_pipeline_registry("")
    with pytest.raises(UnknownPipelineError, match="Available providers"):
        asyncio.run(registry.process(request("missing_pipeline")))


def test_classic_pipeline_keeps_async_server_responsive(monkeypatch) -> None:
    """CPU processing must not occupy FastAPI's event-loop thread."""

    started = threading.Event()
    release = threading.Event()
    expected = object()

    def blocking_classic(*_args):
        started.set()
        release.wait(2)
        return expected

    monkeypatch.setattr("app.pipelines.builtins.process_classic", blocking_classic)

    async def scenario():
        task = asyncio.create_task(ClassicPipeline().process(request("classic")))
        before = time.perf_counter()
        assert await asyncio.to_thread(started.wait, 0.5)
        # This coroutine can resume immediately only when blocking_classic is
        # running in a worker thread rather than on the event loop.
        elapsed = time.perf_counter() - before
        release.set()
        assert await task is expected
        return elapsed

    assert asyncio.run(scenario()) < 0.5
