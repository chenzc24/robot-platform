"""Immutable image-to-stroke artifacts from the loopback StrokeReview API."""

import hashlib
import json
import mimetypes
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import DrawingError


def _loopback_endpoint(base_url):
    parsed = urlparse(str(base_url))
    if parsed.scheme not in ("http", "https") or parsed.hostname not in (
        "127.0.0.1", "localhost", "::1",
    ):
        raise DrawingError("strokereview_api_must_be_loopback")
    return str(base_url).rstrip("/") + "/api/v1/process"


def _multipart(image_path, parameters):
    boundary = "----robot-drawing-%s" % uuid.uuid4().hex
    content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    parts = []

    def add(value):
        parts.append(value if isinstance(value, bytes) else value.encode("utf-8"))

    add("--%s\r\n" % boundary)
    add('Content-Disposition: form-data; name="parameters"\r\n\r\n')
    add(json.dumps(parameters, ensure_ascii=False))
    add("\r\n--%s\r\n" % boundary)
    add(
        'Content-Disposition: form-data; name="file"; filename="%s"\r\n'
        % image_path.name.replace('"', "").replace("\r", "").replace("\n", "")
    )
    add("Content-Type: %s\r\n\r\n" % content_type)
    add(image_path.read_bytes())
    add("\r\n--%s--\r\n" % boundary)
    return b"".join(parts), "multipart/form-data; boundary=%s" % boundary


def _write_immutable(path, document):
    encoded = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if path.exists():
        if path.read_bytes() != encoded:
            raise DrawingError("generated_artifact_conflict:%s" % path.name)
        return
    path.write_bytes(encoded)


def process_image_to_artifacts(
    image_path,
    output_dir,
    canvas_width_mm,
    canvas_height_mm,
    provider="classic",
    base_url="http://127.0.0.1:8000",
    extra_parameters=None,
    timeout_seconds=600.0,
    opener=urlopen,
):
    """Process one image and preserve the response, strokes and audit JSON."""
    image_path = Path(image_path).resolve()
    if not image_path.is_file():
        raise DrawingError("input_image_not_found")
    if image_path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".svg", ".webp"):
        raise DrawingError("unsupported_image_input")
    if not isinstance(extra_parameters, dict):
        if extra_parameters is not None:
            raise DrawingError("image_parameters_must_be_object")
        extra_parameters = {}
    parameters = dict(extra_parameters)
    parameters.update({
        "provider": provider,
        "target_width_mm": float(canvas_width_mm),
        "target_height_mm": float(canvas_height_mm),
    })
    body, content_type = _multipart(image_path, parameters)
    request = Request(
        _loopback_endpoint(base_url), data=body, method="POST",
        headers={"Content-Type": content_type, "Accept": "application/json"},
    )
    try:
        with opener(request, timeout=float(timeout_seconds)) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise DrawingError("strokereview_http_%d" % error.code) from error
    except (URLError, OSError) as error:
        raise DrawingError("strokereview_unavailable") from error
    except (UnicodeError, json.JSONDecodeError) as error:
        raise DrawingError("strokereview_invalid_response") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("strokes_document"), dict):
        raise DrawingError("strokereview_missing_strokes_document")
    if not isinstance(payload.get("audit_document"), dict):
        raise DrawingError("strokereview_missing_audit_document")

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    manifest = {
        "source_name": image_path.name,
        "source_sha256": source_sha256,
        "parameters": parameters,
    }
    _write_immutable(output_dir / "process-response.json", payload)
    _write_immutable(output_dir / "strokes.json", payload["strokes_document"])
    _write_immutable(output_dir / "audit.json", payload["audit_document"])
    _write_immutable(output_dir / "input-manifest.json", manifest)
    return {
        "drawing_path": output_dir / "strokes.json",
        "audit_path": output_dir / "audit.json",
        "response_path": output_dir / "process-response.json",
        "manifest_path": output_dir / "input-manifest.json",
        "source_sha256": source_sha256,
        "parameters": parameters,
    }


def validate_job_canvas(
    job, drawing_config, tolerance_mm=0.01, allow_uniform_rescale=False,
):
    """Reject silent scale/stretch between JSON canvas and the physical board."""
    expected = (
        drawing_config.geometry.canvas_width_mm,
        drawing_config.geometry.canvas_height_mm,
    )
    actual = (job.canvas.target_width_mm, job.canvas.target_height_mm)
    exact = not any(
        abs(left - right) > tolerance_mm for left, right in zip(actual, expected)
    )
    scale = 1.0
    if not exact:
        scale_x = expected[0] / actual[0]
        scale_y = expected[1] / actual[1]
        if not allow_uniform_rescale or abs(scale_x - scale_y) > 1e-6:
            raise DrawingError(
                "drawing_board_size_mismatch:json=%gx%g,config=%gx%g"
                % (actual[0], actual[1], expected[0], expected[1])
            )
        scale = scale_x
    return {
        "width_mm": expected[0],
        "height_mm": expected[1],
        "json_origin_user_y_mm": drawing_config.geometry.user_y_offset_mm,
        "json_origin_user_z_mm": (
            drawing_config.geometry.user_z_offset_mm
            + drawing_config.geometry.canvas_height_mm
        ),
        "json_x_maps_to": "+UserY",
        "json_y_maps_to": "-UserZ",
        "json_canvas_mm": [actual[0], actual[1]],
        "uniform_canvas_scale": scale,
    }
