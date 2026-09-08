"""Minimal working full-pipeline plugin.

Load for development with:
STROKE_PIPELINE_PLUGINS=examples.custom_pipeline:create_pipeline

Replace the body of PartnerExamplePipeline.process with a real model. The core
application, API routes, audit contract and frontend do not need to change.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from app.pipelines import (
    PipelineMetadata,
    PipelineRequest,
    PipelineStroke,
    build_pipeline_response,
)


class PartnerExamplePipeline:
    metadata = PipelineMetadata(
        id="partner_example",
        label="伙伴算法示例",
        description="演示完整图片到笔触插件接口；默认只输出一条对角线",
        implementation="examples.custom_pipeline.PartnerExamplePipeline",
    )

    async def process(self, request: PipelineRequest):
        with Image.open(BytesIO(request.content)) as image:
            source_width, source_height = image.size
        canvas_width = source_width / max(source_width, source_height)
        canvas_height = source_height / max(source_width, source_height)
        # Replace this candidate list with your model's normalized stroke output.
        candidates = [
            PipelineStroke(
                points=[
                    (canvas_width * 0.1, canvas_height * 0.1),
                    (canvas_width * 0.9, canvas_height * 0.9),
                ],
                confidence=1.0,
                source_ref="partner_example",
            )
        ]
        return build_pipeline_response(
            request,
            actual_provider=self.metadata.id,
            source_width=source_width,
            source_height=source_height,
            strokes=candidates,
            warnings=["example_pipeline_output"],
        )


def create_pipeline() -> PartnerExamplePipeline:
    return PartnerExamplePipeline()
