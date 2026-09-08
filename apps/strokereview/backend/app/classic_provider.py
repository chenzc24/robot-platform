"""经典栅格图片转笔触流程。

处理链：Pillow 解码和方向纠正；OpenCV 灰度化、增强、降噪和二值化；
scikit-image 清理小区域；opencv-contrib Zhang-Suen 细化为单像素骨架；
Skan 提取骨架分支；NetworkX 在交叉点配对；OpenCV/SciPy 简化和平滑；
最后由本项目规则评分、归一化并生成正式笔触与审核数据。

深度模型也复用本文件：模型只替换“图片提取线稿”步骤，骨架到笔触的
处理仍由这里完成。因此这是当前 PNG/JPG 转笔触最核心的实现文件。
"""

from __future__ import annotations

import base64
import heapq
import hashlib
import json
import math
import warnings
from dataclasses import dataclass
from io import BytesIO

import cv2
import networkx as nx
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from scipy.interpolate import make_splprep
from scipy.spatial import cKDTree
from skan import Skeleton
from skimage.morphology import remove_small_holes, remove_small_objects

from .models import (
    AuditDocument,
    AuditProcessing,
    AuditScores,
    AuditStroke,
    CanvasSpec,
    Decision,
    DiagnosticImages,
    ProcessingParameters,
    ProcessResponse,
    DrawingStrokeGeometry,
    StrokesDocument,
    StrokeSelectionSummary,
)
from .canvas_layout import fit_canvas_layout


@dataclass(frozen=True)
class Branch:
    """Skan 提取的一段骨架分支；端点一般位于线条末端或交叉点。"""

    id: int
    points: np.ndarray  # xy pixel coordinates
    start_node: int | None = None
    end_node: int | None = None


@dataclass(frozen=True)
class TracedPath:
    """组合后的候选路径，以及图级剪枝给出的可恢复审核提示。"""

    points: np.ndarray
    closed: bool
    decision_hint: Decision | None = None
    reasons: tuple[str, ...] = ()


# 八邻域骨架中，连续像素的最大中心距离是 sqrt(2)。额外的小量只用于
# 吸收浮点误差；超过它就说明两段并不是真正相接的骨架邻居。
MAX_SKELETON_STEP = math.sqrt(2) + 1e-6


def _processing_max_dimension(detail_level: int) -> int:
    return min(3072, 1024 + detail_level * 20)


def decode_raster(content: bytes, max_dimension: int | None = None) -> tuple[np.ndarray, int, int]:
    """解码 PNG/JPG、应用 EXIF，并在转 NumPy 前限制工作尺寸。

    Pillow 的 thumbnail 对 JPEG 还能利用解码器缩放。更重要的是，不再为一张
    超大照片额外创建完整分辨率的 RGB NumPy 数组；原始宽高仍单独保留。
    """

    try:
        with Image.open(BytesIO(content)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            source_width, source_height = image.size
            if max_dimension and max(image.size) > max_dimension:
                image.thumbnail(
                    (max_dimension, max_dimension),
                    Image.Resampling.LANCZOS,
                    reducing_gap=2.0,
                )
            return np.asarray(image).copy(), source_width, source_height
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("The uploaded file is not a decodable PNG or JPEG image") from exc


def _resize_for_processing(image: np.ndarray, detail_level: int) -> np.ndarray:
    """限制工作分辨率，避免超大图片耗尽内存。

    detail_level 越高，允许的工作分辨率越大，能保留更多细节，但也会
    增加骨架像素、候选分支数量和处理时间。
    """

    height, width = image.shape[:2]
    max_dimension = _processing_max_dimension(detail_level)
    if max(height, width) <= max_dimension:
        return image
    scale = max_dimension / max(height, width)
    return cv2.resize(
        image,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )


def extract_classic_lineart(
    image: np.ndarray, parameters: ProcessingParameters
) -> tuple[np.ndarray, np.ndarray]:
    """用经典图像处理生成二值线稿和逐像素置信度。

    mask 中 True 表示线条；confidence 为 0~1，越大表示该位置越像深色线。
    """

    # OpenCV：彩色转灰度；CLAHE 用于改善扫描稿局部明暗不均。
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(
        clipLimit=1.5 + parameters.detail_level / 50,
        tileGridSize=(8, 8),
    )
    enhanced = clahe.apply(gray)
    # 轻微高斯模糊压低扫描颗粒，再由 Otsu 自动寻找二值化阈值。
    denoised = cv2.GaussianBlur(enhanced, (3, 3), 0)
    # 自动判断白底黑线或黑底白线，最终统一为 True=线条。
    dark_lines = float(np.mean(denoised)) >= 127
    threshold_mode = cv2.THRESH_BINARY_INV if dark_lines else cv2.THRESH_BINARY
    _, binary_u8 = cv2.threshold(denoised, 0, 255, threshold_mode | cv2.THRESH_OTSU)
    mask = binary_u8 > 0

    # 从目标绘图毫米尺寸推导清理阈值，而不是使用固定像素常量。
    physical_layout = fit_canvas_layout(image.shape[1], image.shape[0], parameters)
    pixels_per_mm = 1.0 / physical_layout.millimeters_per_source_unit
    subresolution_area = max(
        1,
        round(
            (parameters.effective_resolution_mm * pixels_per_mm) ** 2
            * (0.25 + parameters.cleanup_strength / 100)
        ),
    )
    # scikit-image：删除小前景连通域并填补小孔洞，八邻域视为相连。
    mask = remove_small_objects(mask, max_size=subresolution_area, connectivity=2)
    hole_area = max(1, round(subresolution_area * 0.75))
    mask = remove_small_holes(mask, max_size=hole_area, connectivity=2)

    if parameters.cleanup_strength >= 70:
        # 高清理强度下使用 OpenCV 闭运算，连接约 1 像素的小裂缝。
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel) > 0

    # 经典流程用增强后的前景/背景对比近似置信度；它不是神经网络概率。
    # 极性必须与 Otsu 最终选择一致：白底黑线看“黑度”，黑底白线看“亮度”。
    enhanced_float = enhanced.astype(np.float32)
    confidence = (
        (255.0 - enhanced_float) / 255.0
        if dark_lines
        else enhanced_float / 255.0
    )
    return mask, confidence


def skeletonize_mask(mask: np.ndarray) -> np.ndarray:
    """调用 opencv-contrib 的 Zhang-Suen thinning 得到单像素中心线。"""

    skeleton_u8 = cv2.ximgproc.thinning(
        mask.astype(np.uint8) * 255,
        thinningType=cv2.ximgproc.THINNING_ZHANGSUEN,
    )
    return skeleton_u8 > 0


_NEIGHBOR_OFFSETS = tuple(
    (dy, dx)
    for dy in (-1, 0, 1)
    for dx in (-1, 0, 1)
    if (dy, dx) != (0, 0)
)


def _pixel_degrees(skeleton: np.ndarray) -> np.ndarray:
    """返回八邻域骨架度数；背景像素保持 0。"""

    neighbor_count = cv2.filter2D(
        skeleton.astype(np.uint8),
        ddepth=cv2.CV_16S,
        kernel=np.ones((3, 3), dtype=np.int16),
        borderType=cv2.BORDER_CONSTANT,
    ) - skeleton.astype(np.int16)
    return np.where(skeleton, neighbor_count, 0).astype(np.int16)


def _junction_clusters(
    skeleton: np.ndarray,
) -> tuple[dict[tuple[int, int], int], dict[int, np.ndarray]]:
    """把相邻的度>=3分叉像素收缩为稳定的逻辑节点。

    端点单独成为节点，避免把真实的一像素末端吞进交叉点。每个分叉团使用
    距离质心最近的骨架像素作为代表，因此所有相连原子分支共享同一坐标。
    """

    degrees = _pixel_degrees(skeleton)
    junction_mask = (skeleton & (degrees >= 3)).astype(np.uint8)
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        junction_mask,
        connectivity=8,
    )
    pixel_to_node: dict[tuple[int, int], int] = {}
    representatives: dict[int, np.ndarray] = {}
    next_node = 0
    for label in range(1, count):
        left = int(stats[label, cv2.CC_STAT_LEFT])
        top = int(stats[label, cv2.CC_STAT_TOP])
        width = int(stats[label, cv2.CC_STAT_WIDTH])
        height = int(stats[label, cv2.CC_STAT_HEIGHT])
        # Searching the whole image once per cluster is quadratic in the number
        # of junctions and made detailed illustrations appear frozen. Restrict
        # each lookup to OpenCV's component bounding box instead.
        coordinates = np.argwhere(
            labels[top : top + height, left : left + width] == label
        )
        coordinates += np.array([top, left], dtype=coordinates.dtype)
        if len(coordinates) == 0:
            continue
        centroid = np.mean(coordinates, axis=0)
        distances = np.sum((coordinates - centroid) ** 2, axis=1)
        candidates = coordinates[np.flatnonzero(np.isclose(distances, np.min(distances)))]
        representative_yx = min((int(y), int(x)) for y, x in candidates)
        representatives[next_node] = np.array(
            [float(representative_yx[1]), float(representative_yx[0])], dtype=np.float64
        )
        for y, x in coordinates:
            pixel_to_node[(int(y), int(x))] = next_node
        next_node += 1

    # Degree 0/1 pixels are real isolated/leaf nodes and must not be clustered
    # with a nearby junction pixel.
    for y, x in np.argwhere(skeleton & (degrees <= 1)):
        key = (int(y), int(x))
        pixel_to_node[key] = next_node
        representatives[next_node] = np.array([float(x), float(y)], dtype=np.float64)
        next_node += 1
    return pixel_to_node, representatives


def _path_endpoint_node(
    point_yx: np.ndarray,
    pixel_to_node: dict[tuple[int, int], int],
    nearby_node_ids: set[int] | None = None,
) -> int | None:
    key = (round(float(point_yx[0])), round(float(point_yx[1])))
    if key in pixel_to_node:
        return pixel_to_node[key]
    # Skan endpoints normally are critical pixels. This one-pixel fallback
    # handles library/version differences without ever joining distant nodes.
    nearby = [
        pixel_to_node[(key[0] + dy, key[1] + dx)]
        for dy, dx in _NEIGHBOR_OFFSETS
        if (key[0] + dy, key[1] + dx) in pixel_to_node
    ]
    if nearby_node_ids is not None:
        nearby = [node for node in nearby if node in nearby_node_ids]
    return min(nearby) if nearby else None


def _extract_atomic_branches(skeleton: np.ndarray) -> list[Branch]:
    """先移除整个分叉像素团，再用 Skan 提取团外原子路径。

    旧实现让 Skan 先遍历原始骨架，之后只把路径首尾坐标改成分叉团代表点。
    因此分叉团内部的三角形/菱形像素环仍会成为独立闭环，复杂插画中会在同一
    位置生成许多几乎重合的小笔触。现在 degree>=3 的相邻像素先整体移出路径
    图；剩余每个分量的端点再接回一个逻辑代表点。团内边不会进入 Skan，而团外
    的真实闭环、T/X 分叉和叶节点仍保留。
    """

    if int(np.count_nonzero(skeleton)) < 2:
        return []
    pixel_to_node, representatives = _junction_clusters(skeleton)
    degrees = _pixel_degrees(skeleton)
    junction_mask = skeleton & (degrees >= 3)
    junction_node_ids = {
        pixel_to_node[(int(y), int(x))]
        for y, x in np.argwhere(junction_mask)
    }
    # This is the actual contraction: Skan never sees edges internal to a
    # junction cluster, so it cannot export them as tiny closed paths.
    path_skeleton = skeleton & ~junction_mask
    branches: list[Branch] = []
    covered_pixels: set[tuple[int, int]] = set()

    def endpoint_node(point_yx: np.ndarray) -> int:
        node = _path_endpoint_node(
            point_yx,
            pixel_to_node,
            junction_node_ids,
        )
        if node is not None:
            return node
        # A path endpoint that is neither an original leaf nor adjacent to a
        # junction is unusual but valid. Give it a deterministic local node.
        key = (round(float(point_yx[0])), round(float(point_yx[1])))
        node = len(representatives)
        pixel_to_node[key] = node
        representatives[node] = np.array([float(key[1]), float(key[0])], dtype=np.float64)
        return node

    def append_branch(coordinates: np.ndarray, start_node: int, end_node: int) -> None:
        xy = np.column_stack((coordinates[:, 1], coordinates[:, 0])).astype(np.float64)
        xy = np.vstack((representatives[start_node], xy, representatives[end_node]))
        keep = np.r_[True, np.linalg.norm(np.diff(xy, axis=0), axis=1) > 1e-9]
        xy = xy[keep]
        if len(xy) < 2:
            return
        branches.append(
            Branch(
                id=len(branches),
                points=xy,
                start_node=start_node,
                end_node=end_node,
            )
        )

    if int(np.count_nonzero(path_skeleton)) >= 2:
        skan_skeleton = Skeleton(path_skeleton.astype(np.uint8))
        for path_index in range(skan_skeleton.n_paths):
            coordinates = skan_skeleton.path_coordinates(path_index)
            if len(coordinates) < 2:
                continue
            covered_pixels.update(
                (round(float(point[0])), round(float(point[1])))
                for point in coordinates
            )
            start_node = endpoint_node(coordinates[0])
            end_node = endpoint_node(coordinates[-1])
            append_branch(coordinates, start_node, end_node)

    # Skan intentionally ignores isolated one-pixel components. After removing a
    # junction cluster, such a pixel can be either a real one-pixel terminal spur
    # or the sole bridge between two logical junctions. Reconnect those cases;
    # ignore a pixel touching only one copy of the same junction, which is merely
    # an internal diagonal-cycle remnant.
    residual = path_skeleton.copy()
    for y, x in covered_pixels:
        if 0 <= y < residual.shape[0] and 0 <= x < residual.shape[1]:
            residual[y, x] = False
    component_count, component_labels, component_stats, _component_centroids = cv2.connectedComponentsWithStats(
        residual.astype(np.uint8),
        connectivity=8,
    )
    for label in range(1, component_count):
        if int(component_stats[label, cv2.CC_STAT_AREA]) != 1:
            continue
        y = int(component_stats[label, cv2.CC_STAT_TOP])
        x = int(component_stats[label, cv2.CC_STAT_LEFT])
        adjacent_junctions = sorted(
            {
                pixel_to_node[(y + dy, x + dx)]
                for dy, dx in _NEIGHBOR_OFFSETS
                if (y + dy, x + dx) in pixel_to_node
                and pixel_to_node[(y + dy, x + dx)] in junction_node_ids
            }
        )
        direct_node = pixel_to_node.get((y, x))
        nodes = list(adjacent_junctions)
        if direct_node is not None and direct_node not in nodes:
            nodes.append(direct_node)
        if len(nodes) < 2:
            continue
        point = np.array([[float(y), float(x)]], dtype=np.float64)
        append_branch(point, nodes[0], nodes[1])
    return branches


def _branch_length_pixels(branch: Branch) -> float:
    return float(np.sum(np.linalg.norm(np.diff(branch.points, axis=0), axis=1)))


def _branch_confidence(branch: Branch, confidence_map: np.ndarray) -> float:
    height, width = confidence_map.shape
    sample = np.clip(
        np.rint(branch.points).astype(int),
        [0, 0],
        [width - 1, height - 1],
    )
    return float(np.mean(confidence_map[sample[:, 1], sample[:, 0]]))


def _node_tangent(
    branch: Branch,
    node_id: int,
    distance_px: float | None = None,
) -> np.ndarray:
    if branch.start_node == node_id:
        return _outward_tangent(branch, True, distance_px=distance_px)
    if branch.end_node == node_id:
        return _outward_tangent(branch, False, distance_px=distance_px)
    return np.array([0.0, 0.0])


def _prune_terminal_spurs(
    branches: list[Branch],
    mm_per_pixel: float,
    confidence_map: np.ndarray,
    parameters: ProcessingParameters,
) -> tuple[list[Branch], list[TracedPath]]:
    """在分叉配对前识别 leaf->junction 短原子分支。

    极短（约一两个像素且<0.8mm）、相对主干很短并位于连续主干侧面的分支
    自动从组合图移除，但仍作为 discard 候选进入 audit。0.8~2mm 只有在同时
    低置信或明显锯齿时才作为 uncertain 移出；同置信度的真实短支线保留。
    """

    if parameters.spur_prune_length_mm <= 0 or not branches:
        return branches, []
    working = list(branches)
    audit_candidates: list[TracedPath] = []
    tangent_distance_px = max(2.0, parameters.pen_width_mm * 4.0) / max(mm_per_pixel, 1e-9)
    # Removing one spur can expose another terminal spur. Rebuild degrees until
    # a complete pass makes no change; every removed path remains auditable.
    while working:
        incident: dict[int, list[Branch]] = {}
        for branch in working:
            for node in (branch.start_node, branch.end_node):
                if node is not None:
                    incident.setdefault(node, []).append(branch)
        removed_this_pass: set[int] = set()
        for branch in sorted(working, key=lambda item: item.id):
            endpoints = (branch.start_node, branch.end_node)
            if endpoints[0] is None or endpoints[1] is None or endpoints[0] == endpoints[1]:
                continue
            degrees = (len(incident.get(endpoints[0], [])), len(incident.get(endpoints[1], [])))
            if min(degrees) != 1 or max(degrees) < 3:
                continue
            junction = endpoints[0] if degrees[0] >= 3 else endpoints[1]
            adjacent = [candidate for candidate in incident[junction] if candidate.id != branch.id]
            if len(adjacent) < 2:
                continue
            length_px = _branch_length_pixels(branch)
            length_mm = length_px * mm_per_pixel
            if length_mm > max(2.0, parameters.spur_prune_length_mm):
                continue
            adjacent_lengths = [_branch_length_pixels(item) for item in adjacent]
            length_ratio = length_px / max(max(adjacent_lengths), 1e-9)
            adjacent_tangents = [
                _node_tangent(item, junction, tangent_distance_px)
                for item in adjacent
            ]
            straightness = max(
                (1.0 - float(np.clip(np.dot(first, second), -1.0, 1.0))) / 2.0
                for index, first in enumerate(adjacent_tangents)
                for second in adjacent_tangents[index + 1 :]
            )
            trunk_is_straight = straightness >= math.cos(math.radians(30.0 / 2.0)) ** 2
            confidence = _branch_confidence(branch, confidence_map)
            adjacent_confidence = float(
                np.median([_branch_confidence(item, confidence_map) for item in adjacent])
            )
            direct = float(np.linalg.norm(branch.points[-1] - branch.points[0]))
            zigzag_ratio = length_px / max(direct, 1e-9)

            ultra_short = length_mm < min(0.8, parameters.spur_prune_length_mm)
            strong_geometry = trunk_is_straight and length_ratio <= 0.30
            weak_signal = confidence + 0.10 < adjacent_confidence or zigzag_ratio >= 1.35
            if ultra_short and strong_geometry:
                decision = Decision.DISCARD
            elif (
                0.8 <= length_mm <= 2.0
                and length_mm <= max(parameters.spur_prune_length_mm, 0.8)
                and strong_geometry
                and weak_signal
            ):
                decision = Decision.UNCERTAIN
            else:
                continue
            removed_this_pass.add(branch.id)
            audit_candidates.append(
                TracedPath(
                    points=branch.points,
                    closed=False,
                    decision_hint=decision,
                    reasons=("pruned_spur",),
                )
            )
        if not removed_this_pass:
            break
        working = [branch for branch in working if branch.id not in removed_this_pass]
    return working, audit_candidates


def _endpoint_key(point: np.ndarray) -> tuple[int, int]:
    return round(float(point[0])), round(float(point[1]))


def _stable_endpoint_tangent(
    points: np.ndarray,
    at_start: bool,
    distance_px: float,
) -> np.ndarray:
    """Fit a stable endpoint-to-interior tangent using PCA over arc length."""

    oriented = points if at_start else points[::-1]
    if len(oriented) < 2:
        return np.array([0.0, 0.0])
    selected = [oriented[0]]
    travelled = 0.0
    for previous, current in zip(oriented, oriented[1:]):
        travelled += float(np.linalg.norm(current - previous))
        selected.append(current)
        if travelled >= max(distance_px, 1.0):
            break
    samples = np.asarray(selected, dtype=np.float64)
    direct = samples[-1] - samples[0]
    if len(samples) >= 3:
        centered = samples - np.mean(samples, axis=0)
        covariance = centered.T @ centered
        values, vectors = np.linalg.eigh(covariance)
        vector = vectors[:, int(np.argmax(values))]
        if float(np.dot(vector, direct)) < 0:
            vector = -vector
    else:
        vector = direct
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else np.array([0.0, 0.0])


def _outward_tangent(
    branch: Branch,
    at_start: bool,
    window: int = 5,
    *,
    distance_px: float | None = None,
) -> np.ndarray:
    """Estimate the endpoint-to-interior direction on a physical-length window."""

    if distance_px is None:
        distance_px = float(max(1, window))
    return _stable_endpoint_tangent(branch.points, at_start, distance_px)


def _junction_pairs(
    branches: list[Branch],
    *,
    mm_per_pixel: float = 1.0,
    confidence_map: np.ndarray | None = None,
    parameters: ProcessingParameters | None = None,
) -> dict[tuple[int, int], tuple[int, int]]:
    """在每个交叉点为分支端口寻找几何上最自然的两两配对。

    NetworkX 的最小权重匹配负责求最佳组合；本项目定义匹配代价：两段
    切线越接近一条直线，代价越低。因此十字倾向组成横、竖两笔，T 形
    倾向保持直线主干连续。微小 tie_break 只用于让相同输入结果确定。
    """

    nodes: dict[tuple[int, int], list[tuple[int, int]]] = {}
    branch_by_id = {branch.id: branch for branch in branches}
    for branch in branches:
        nodes.setdefault(_endpoint_key(branch.points[0]), []).append((branch.id, 0))
        nodes.setdefault(_endpoint_key(branch.points[-1]), []).append((branch.id, 1))

    result: dict[tuple[int, int], tuple[int, int]] = {}
    tangent_distance_mm = (
        max(2.0, parameters.pen_width_mm * 4.0)
        if parameters is not None
        else max(2.0, mm_per_pixel * 5.0)
    )
    tangent_distance_px = tangent_distance_mm / max(mm_per_pixel, 1e-9)
    for ports in nodes.values():
        if len(ports) < 2:
            continue
        if len(ports) == 2:
            first_port, second_port = ports
            first_branch = branch_by_id[first_port[0]]
            second_branch = branch_by_id[second_port[0]]
            first_point = first_branch.points[0 if first_port[1] == 0 else -1]
            second_point = second_branch.points[0 if second_port[1] == 0 else -1]
            if float(np.linalg.norm(first_point - second_point)) <= MAX_SKELETON_STEP:
                result[first_port] = second_port
                result[second_port] = first_port
            continue
        candidate_graph = nx.Graph()
        candidate_graph.add_nodes_from(range(len(ports)))
        for first in range(len(ports)):
            for second in range(first + 1, len(ports)):
                first_id, first_end = ports[first]
                second_id, second_end = ports[second]
                first_point = branch_by_id[first_id].points[0 if first_end == 0 else -1]
                second_point = branch_by_id[second_id].points[0 if second_end == 0 else -1]
                # 正常情况下同一 Skan 节点的端点完全重合。这里仍显式检查
                # 几何距离，防止未来更换骨架库或坐标量化方式后误连远端分支。
                if float(np.linalg.norm(first_point - second_point)) > MAX_SKELETON_STEP:
                    continue
                tangent_a = _outward_tangent(
                    branch_by_id[first_id], first_end == 0, distance_px=tangent_distance_px
                )
                tangent_b = _outward_tangent(
                    branch_by_id[second_id], second_end == 0, distance_px=tangent_distance_px
                )
                direction_continuity = (
                    1.0 - float(np.clip(np.dot(tangent_a, tangent_b), -1.0, 1.0))
                ) / 2.0
                support_mm = min(
                    _branch_length_pixels(branch_by_id[first_id]),
                    _branch_length_pixels(branch_by_id[second_id]),
                ) * mm_per_pixel
                support = float(np.clip(support_mm / max(tangent_distance_mm * 2.0, 1e-9), 0.0, 1.0))
                if confidence_map is None:
                    confidence = 1.0
                else:
                    confidence = (
                        _branch_confidence(branch_by_id[first_id], confidence_map)
                        + _branch_confidence(branch_by_id[second_id], confidence_map)
                    ) / 2.0
                score = 0.70 * direction_continuity + 0.20 * support + 0.10 * confidence
                tie_break = (first * len(ports) + second) * 1e-12
                candidate_graph.add_edge(first, second, weight=score - tie_break)
        for first, second in nx.max_weight_matching(
            candidate_graph,
            maxcardinality=True,
            weight="weight",
        ):
            first_port, second_port = ports[first], ports[second]
            result[first_port] = second_port
            result[second_port] = first_port
    return result


def _combine_branches(
    branches: list[Branch],
    *,
    mm_per_pixel: float = 1.0,
    confidence_map: np.ndarray | None = None,
    parameters: ProcessingParameters | None = None,
) -> list[tuple[np.ndarray, bool]]:
    """按照交叉点配对结果，把短分支拼成一次落笔可画完的连续笔触。"""

    if not branches:
        return []
    branch_by_id = {branch.id: branch for branch in branches}
    if mm_per_pixel == 1.0 and confidence_map is None and parameters is None:
        # Preserve the small public/testing seam used by existing integrations.
        paired = _junction_pairs(branches)
    else:
        paired = _junction_pairs(
            branches,
            mm_per_pixel=mm_per_pixel,
            confidence_map=confidence_map,
            parameters=parameters,
        )
    used: set[int] = set()
    combined: list[tuple[np.ndarray, bool]] = []

    # 优先从未配对端口（自然端点）开始；最后剩下的通常是闭合环。
    unpaired_ports = [
        (branch.id, end)
        for branch in branches
        for end in (0, 1)
        if (branch.id, end) not in paired
    ]
    starts = sorted(unpaired_ports) + [(branch.id, 0) for branch in branches]
    for branch_id, start_end in starts:
        if branch_id in used:
            continue
        assembled: list[np.ndarray] = []
        current = (branch_id, start_end)
        # 每段分支都允许反向使用，以保证前一段终点与后一段起点重合。
        while current[0] not in used:
            current_id, current_start = current
            branch = branch_by_id[current_id]
            oriented = branch.points if current_start == 0 else branch.points[::-1]
            if assembled:
                gap = float(np.linalg.norm(assembled[-1] - oriented[0]))
                # 即使配对表意外包含坏连接，也绝不在结果中画出跨越空白的长线。
                # 当前分支保持未使用，稍后会作为另一条独立笔触处理。
                if gap > MAX_SKELETON_STEP:
                    break
                if np.allclose(assembled[-1], oriented[0]):
                    assembled.extend(oriented[1:])
                else:
                    assembled.extend(oriented)
            else:
                assembled.extend(oriented)
            used.add(current_id)
            exit_port = (current_id, 1 - current_start)
            if exit_port not in paired:
                break
            current = paired[exit_port]

        points = np.asarray(assembled, dtype=np.float64)
        closed = bool(len(points) > 2 and np.linalg.norm(points[0] - points[-1]) <= math.sqrt(2))
        if closed:
            points[-1] = points[0]
        combined.append((points, closed))
    return combined


def _join_physical_gaps(
    paths: list[TracedPath],
    line_mask: np.ndarray,
    mm_per_pixel: float,
    parameters: ProcessingParameters,
) -> list[TracedPath]:
    """Conservatively join collinear endpoints separated by at most one pen width."""

    if len(paths) < 2 or parameters.pen_width_mm <= 0:
        return paths
    maximum_gap_px = parameters.pen_width_mm / max(mm_per_pixel, 1e-9)
    if maximum_gap_px <= MAX_SKELETON_STEP:
        return paths
    radius = max(1, int(math.ceil(maximum_gap_px / 2.0)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1))
    permitted = cv2.dilate((np.asarray(line_mask) > 0).astype(np.uint8), kernel) > 0
    tangent_distance_px = max(2.0, parameters.pen_width_mm * 4.0) / max(mm_per_pixel, 1e-9)
    minimum_alignment = math.cos(math.radians(20.0))
    current = list(paths)
    while True:
        candidates: list[tuple[float, float, int, int, int, int]] = []
        for first_index, first_path in enumerate(current):
            if first_path.closed:
                continue
            for second_index in range(first_index + 1, len(current)):
                second_path = current[second_index]
                if second_path.closed:
                    continue
                for first_end in (0, 1):
                    first_point = first_path.points[0 if first_end == 0 else -1]
                    first_tangent = _stable_endpoint_tangent(
                        first_path.points, first_end == 0, tangent_distance_px
                    )
                    for second_end in (0, 1):
                        second_point = second_path.points[0 if second_end == 0 else -1]
                        gap_vector = second_point - first_point
                        gap = float(np.linalg.norm(gap_vector))
                        if gap <= MAX_SKELETON_STEP or gap > maximum_gap_px:
                            continue
                        gap_direction = gap_vector / gap
                        second_tangent = _stable_endpoint_tangent(
                            second_path.points, second_end == 0, tangent_distance_px
                        )
                        if (
                            float(np.dot(first_tangent, gap_direction)) > -minimum_alignment
                            or float(np.dot(second_tangent, gap_direction)) < minimum_alignment
                            or float(np.dot(first_tangent, second_tangent)) > -minimum_alignment
                        ):
                            continue
                        samples = np.linspace(first_point, second_point, max(4, int(math.ceil(gap)) * 2))
                        xy = np.rint(samples).astype(np.int32)
                        xy[:, 0] = np.clip(xy[:, 0], 0, permitted.shape[1] - 1)
                        xy[:, 1] = np.clip(xy[:, 1], 0, permitted.shape[0] - 1)
                        if float(np.mean(permitted[xy[:, 1], xy[:, 0]])) < 0.90:
                            continue
                        alignment = -float(np.dot(first_tangent, second_tangent))
                        candidates.append(
                            (gap, -alignment, first_index, first_end, second_index, second_end)
                        )
        if not candidates:
            break
        _gap, _alignment, first_index, first_end, second_index, second_end = min(candidates)
        first_path = current[first_index]
        second_path = current[second_index]
        first_points = first_path.points if first_end == 1 else first_path.points[::-1]
        second_points = second_path.points if second_end == 0 else second_path.points[::-1]
        merged_points = np.vstack((first_points, second_points))
        hints = [first_path.decision_hint, second_path.decision_hint]
        decision_hint = (
            Decision.DISCARD
            if Decision.DISCARD in hints
            else Decision.UNCERTAIN if Decision.UNCERTAIN in hints else None
        )
        reasons = tuple(dict.fromkeys((*first_path.reasons, *second_path.reasons, "physical_gap_join")))
        merged = TracedPath(
            points=merged_points,
            closed=False,
            decision_hint=decision_hint,
            reasons=reasons,
        )
        current = [
            path for index, path in enumerate(current)
            if index not in {first_index, second_index}
        ]
        current.append(merged)
    return current


def trace_skeleton(
    skeleton: np.ndarray,
    *,
    mm_per_pixel: float = 1.0,
    confidence_map: np.ndarray | None = None,
    parameters: ProcessingParameters | None = None,
    line_mask: np.ndarray | None = None,
) -> list[TracedPath]:
    """分叉团收缩 -> 原子分支 -> 毛刺剪枝 -> 配对 -> 连续笔触。"""

    branches = _extract_atomic_branches(skeleton)
    pruned: list[TracedPath] = []
    if confidence_map is not None and parameters is not None:
        branches, pruned = _prune_terminal_spurs(
            branches,
            mm_per_pixel,
            confidence_map,
            parameters,
        )
    combined = [
        TracedPath(points=points, closed=closed)
        for points, closed in _combine_branches(
            branches,
            mm_per_pixel=mm_per_pixel,
            confidence_map=confidence_map,
            parameters=parameters,
        )
        if len(points) >= 2
    ]
    if line_mask is not None and parameters is not None:
        combined = _join_physical_gaps(combined, line_mask, mm_per_pixel, parameters)
    # Pruned candidates remain independently reviewable and recoverable, but
    # they no longer influence junction pairing of the main structure.
    return combined + pruned


def _smooth_and_simplify(
    points: np.ndarray,
    closed: bool,
    parameters: ProcessingParameters,
    mm_per_pixel: float = 1.0,
) -> np.ndarray:
    """按物理容差完成“平滑 -> 误差简化 -> 最长段补点”。

    ``detail_level`` 不再参与几何点密度。SciPy 样条仅生成内部高精度参考曲线，
    最终点数由毫米尺度的 RDP 弦误差和最大段长共同决定。开放端点、闭环接缝和
    明显尖角作为锚点精确保留；任何安全检查失败都会先尝试较弱平滑，最后退回
    原始骨架的误差控制简化折线。
    """

    source = _dedupe_path(points, closed)
    if len(source) < 3:
        return source
    mm_per_pixel = max(float(mm_per_pixel), 1e-9)
    geometry_tolerance_px = parameters.geometry_tolerance_mm / mm_per_pixel
    max_segment_px = parameters.max_segment_length_mm / mm_per_pixel
    anchors = _corner_anchor_indices(source, closed, mm_per_pixel)

    # The old smoothing slider remains as a compatibility strength multiplier.
    # At its historical default (25) the requested physical tolerance is used
    # exactly; zero still disables spline smoothing.
    if parameters.smoothing > 0 and parameters.smooth_tolerance_mm > 0:
        legacy_scale = float(np.clip(math.sqrt(parameters.smoothing / 25.0), 0.25, 2.0))
        requested_tolerance_px = (
            parameters.smooth_tolerance_mm * legacy_scale / mm_per_pixel
        )
        for tolerance_px in (requested_tolerance_px, requested_tolerance_px * 0.5):
            try:
                spans, periodic = _smoothed_spans(source, closed, anchors, tolerance_px)
                dense = _combine_spans(spans, closed)
                simplified = _simplify_spans(
                    spans,
                    closed,
                    periodic,
                    geometry_tolerance_px,
                )
                output = _subdivide_long_segments(simplified, max_segment_px, closed)
                if _geometry_is_safe(
                    output,
                    dense,
                    source,
                    closed,
                    anchors,
                    geometry_tolerance_px,
                    mm_per_pixel,
                ):
                    return output
            except (ValueError, TypeError, RuntimeWarning, np.linalg.LinAlgError):
                continue

    # Safe fallback: no spline. RDP still uses the independent physical geometry
    # tolerance and preserves every protected corner by simplifying span-by-span.
    raw_spans, periodic = _raw_spans(source, closed, anchors)
    fallback = _simplify_spans(
        raw_spans,
        closed,
        periodic,
        geometry_tolerance_px,
    )
    fallback = _subdivide_long_segments(fallback, max_segment_px, closed)
    if _geometry_is_safe(
        fallback,
        source,
        source,
        closed,
        anchors,
        geometry_tolerance_px,
        mm_per_pixel,
        allow_existing_self_intersections=True,
    ):
        return fallback
    return source


def _dedupe_path(points: np.ndarray, closed: bool) -> np.ndarray:
    """删除相邻重复点，并把闭环统一成“首点在末尾重复一次”。"""

    values = np.asarray(points, dtype=np.float64).reshape((-1, 2))
    if len(values) == 0:
        return values
    keep = np.r_[True, np.linalg.norm(np.diff(values, axis=0), axis=1) > 1e-9]
    values = values[keep]
    if closed:
        if len(values) > 1 and np.allclose(values[0], values[-1]):
            values = values[:-1]
        if len(values) >= 3:
            values = np.vstack((values, values[0]))
    return values


def _path_length(points: np.ndarray) -> float:
    return float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1))) if len(points) > 1 else 0.0


def _corner_anchor_indices(
    points: np.ndarray,
    closed: bool,
    mm_per_pixel: float,
) -> list[int]:
    """用约 0.75mm 的观察窗口识别真实尖角，而不是锚定逐像素锯齿。

    单像素台阶在较大窗口内方向接近直线，不会阻止平滑；持续存在的约 55° 以上
    转折会被作为锚点。开放笔触首尾由分段逻辑天然保护，不列入此返回值。
    """

    body = points[:-1] if closed and np.allclose(points[0], points[-1]) else points
    count = len(body)
    if count < 5:
        return []
    # At low processing resolutions a two-pixel window still sees every digital
    # staircase as a 90-degree turn. Four pixels is the minimum stable window;
    # physical scaling then expands it for high-resolution inputs.
    window = min(12, max(4, math.ceil(1.0 / max(mm_per_pixel, 1e-9))))
    candidates: list[tuple[float, int]] = []
    indices = range(count) if closed else range(window, count - window)
    for index in indices:
        left = (index - window) % count
        right = (index + window) % count
        incoming = body[index] - body[left]
        outgoing = body[right] - body[index]
        left_norm = float(np.linalg.norm(incoming))
        right_norm = float(np.linalg.norm(outgoing))
        if min(left_norm, right_norm) < max(1.5, window * 0.45):
            continue
        dot = float(np.clip(np.dot(incoming, outgoing) / (left_norm * right_norm), -1.0, 1.0))
        deflection = math.acos(dot)
        if deflection >= math.radians(55):
            candidates.append((deflection, index))

    # A broad corner can trigger several nearby indices. Keep the sharpest one
    # deterministically so it becomes one protected logical anchor.
    selected: list[int] = []
    for _, index in sorted(candidates, key=lambda item: (-item[0], item[1])):
        if all(min((index - other) % count, (other - index) % count) > window for other in selected):
            selected.append(index)
    return sorted(selected)


def _dense_sample_count(points: np.ndarray, tolerance_px: float, closed: bool) -> int:
    """内部求值足够密，但该数量不会直接成为导出坐标数量。"""

    length = _path_length(points)
    chord = max(0.20, min(1.0, tolerance_px / 3.0))
    minimum = 32 if closed else 2
    return min(16384, max(minimum, len(points) * 2, math.ceil(length / chord) + 1))


def _fit_open_span(points: np.ndarray, tolerance_px: float) -> np.ndarray:
    if len(points) < 4 or _path_length(points) <= 1e-9:
        return points.copy()
    degree = min(3, len(points) - 1)
    smoothing_error = len(points) * tolerance_px**2
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        spline, _ = make_splprep(points.T, k=degree, s=smoothing_error)
    positions = np.linspace(0.0, 1.0, _dense_sample_count(points, tolerance_px, False))
    result = np.asarray(spline(positions)).T
    # Distribute endpoint corrections continuously. This preserves endpoints
    # exactly without creating the long first/last jump caused by hard replacement.
    result += (
        (1.0 - positions)[:, None] * (points[0] - result[0])
        + positions[:, None] * (points[-1] - result[-1])
    )
    result[0], result[-1] = points[0], points[-1]
    return result


def _fit_periodic_span(points: np.ndarray, tolerance_px: float) -> np.ndarray:
    body = points[:-1] if np.allclose(points[0], points[-1]) else points
    if len(body) < 4:
        return np.vstack((body, body[0]))
    smoothing_error = len(body) * tolerance_px**2
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        spline, _ = make_splprep(
            body.T,
            k=min(3, len(body) - 1),
            s=smoothing_error,
            bc_type="periodic",
        )
    positions = np.linspace(
        0.0,
        1.0,
        _dense_sample_count(np.vstack((body, body[0])), tolerance_px, True),
        endpoint=False,
    )
    result = np.asarray(spline(positions)).T
    return np.vstack((result, result[0]))


def _raw_spans(
    source: np.ndarray,
    closed: bool,
    anchors: list[int],
) -> tuple[list[np.ndarray], bool]:
    body = source[:-1] if closed and np.allclose(source[0], source[-1]) else source
    if closed and not anchors:
        return [np.vstack((body, body[0]))], True
    if closed:
        boundaries = anchors or [0]
        spans = []
        for position, start in enumerate(boundaries):
            end = boundaries[(position + 1) % len(boundaries)]
            indices = [start]
            cursor = start
            while cursor != end or len(indices) == 1:
                cursor = (cursor + 1) % len(body)
                indices.append(cursor)
                if len(indices) > len(body) + 1:
                    break
            spans.append(body[indices])
        return spans, False
    boundaries = sorted(set([0, *anchors, len(body) - 1]))
    return [body[start : end + 1] for start, end in zip(boundaries, boundaries[1:])], False


def _smoothed_spans(
    source: np.ndarray,
    closed: bool,
    anchors: list[int],
    tolerance_px: float,
) -> tuple[list[np.ndarray], bool]:
    spans, periodic = _raw_spans(source, closed, anchors)
    if periodic:
        return [_fit_periodic_span(spans[0], tolerance_px)], True
    return [_fit_open_span(span, tolerance_px) for span in spans], False


def _combine_spans(spans: list[np.ndarray], closed: bool) -> np.ndarray:
    assembled: list[np.ndarray] = []
    for span in spans:
        if len(span) == 0:
            continue
        if assembled and np.allclose(assembled[-1], span[0]):
            assembled.extend(span[1:])
        else:
            assembled.extend(span)
    result = np.asarray(assembled, dtype=np.float64)
    if closed and len(result) >= 3:
        if not np.allclose(result[0], result[-1]):
            result = np.vstack((result, result[0]))
        else:
            result[-1] = result[0]
    return result


def _rdp(points: np.ndarray, epsilon: float, closed: bool) -> np.ndarray:
    if len(points) < 3:
        return points.copy()
    body = points[:-1] if closed and np.allclose(points[0], points[-1]) else points
    if len(body) < 3:
        return points.copy()
    simplified = cv2.approxPolyDP(
        body.astype(np.float32).reshape((-1, 1, 2)),
        epsilon=max(float(epsilon), 1e-6),
        closed=closed,
    ).reshape((-1, 2)).astype(np.float64)
    if not closed:
        simplified[0], simplified[-1] = body[0], body[-1]
    elif len(simplified) >= 3:
        simplified = np.vstack((simplified, simplified[0]))
    return simplified


def _simplify_spans(
    spans: list[np.ndarray],
    closed: bool,
    periodic: bool,
    epsilon: float,
) -> np.ndarray:
    if periodic:
        return _rdp(spans[0], epsilon, True)
    simplified = [_rdp(span, epsilon, False) for span in spans]
    return _combine_spans(simplified, closed)


def _subdivide_long_segments(points: np.ndarray, maximum: float, closed: bool) -> np.ndarray:
    """RDP 后只为满足下游最大段长补点；直线不会恢复为逐像素坐标。"""

    if len(points) < 2 or maximum <= 0:
        return points
    result = [points[0]]
    for start, end in zip(points, points[1:]):
        length = float(np.linalg.norm(end - start))
        pieces = max(1, math.ceil(length / maximum))
        for index in range(1, pieces + 1):
            result.append(start + (end - start) * (index / pieces))
    values = np.asarray(result, dtype=np.float64)
    if closed:
        values[-1] = values[0]
    return values


def _max_distance_to_polyline(query: np.ndarray, polyline: np.ndarray) -> float:
    """计算点集到折线的最大欧氏距离，分块避免大图产生巨型临时矩阵。"""

    if len(query) == 0 or len(polyline) < 2:
        return math.inf
    starts = polyline[:-1]
    vectors = polyline[1:] - starts
    squared = np.sum(vectors * vectors, axis=1)
    maximum = 0.0
    for offset in range(0, len(query), 256):
        chunk = query[offset : offset + 256]
        relative = chunk[:, None, :] - starts[None, :, :]
        projection = np.divide(
            np.sum(relative * vectors[None, :, :], axis=2),
            squared[None, :],
            out=np.zeros((len(chunk), len(starts)), dtype=np.float64),
            where=squared[None, :] > 1e-18,
        )
        projection = np.clip(projection, 0.0, 1.0)
        closest = starts[None, :, :] + projection[:, :, None] * vectors[None, :, :]
        distances = np.linalg.norm(chunk[:, None, :] - closest, axis=2)
        maximum = max(maximum, float(np.max(np.min(distances, axis=1))))
    return maximum


def _proper_segment_intersection(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> bool:
    def cross(first: np.ndarray, second: np.ndarray, third: np.ndarray) -> float:
        first_vector = second - first
        second_vector = third - first
        return float(
            first_vector[0] * second_vector[1]
            - first_vector[1] * second_vector[0]
        )

    ab_c, ab_d = cross(a, b, c), cross(a, b, d)
    cd_a, cd_b = cross(c, d, a), cross(c, d, b)
    return ab_c * ab_d < -1e-9 and cd_a * cd_b < -1e-9


def _has_proper_self_intersection(points: np.ndarray, closed: bool) -> bool:
    """检测样条新增的真正穿越；相邻段共享端点不算自交。"""

    segment_count = len(points) - 1
    if segment_count < 3:
        return False
    for first in range(segment_count):
        a, b = points[first], points[first + 1]
        for second in range(first + 2, segment_count):
            if closed and first == 0 and second == segment_count - 1:
                continue
            c, d = points[second], points[second + 1]
            if max(min(a[0], b[0]), min(c[0], d[0])) > min(max(a[0], b[0]), max(c[0], d[0])):
                continue
            if max(min(a[1], b[1]), min(c[1], d[1])) > min(max(a[1], b[1]), max(c[1], d[1])):
                continue
            if _proper_segment_intersection(a, b, c, d):
                return True
    return False


def _geometry_is_safe(
    output: np.ndarray,
    dense_curve: np.ndarray,
    original: np.ndarray,
    closed: bool,
    anchors: list[int],
    geometry_tolerance_px: float,
    mm_per_pixel: float,
    *,
    allow_existing_self_intersections: bool = False,
) -> bool:
    """拒绝越界、偏离、端点漂移、切角、自交、振荡和异常长跳跃。"""

    if len(output) < 2 or not np.all(np.isfinite(output)) or not np.all(np.isfinite(dense_curve)):
        return False
    source_body = original[:-1] if closed and np.allclose(original[0], original[-1]) else original
    allowed_deviation = max(geometry_tolerance_px, 0.30 / max(mm_per_pixel, 1e-9))
    if _max_distance_to_polyline(dense_curve, original) > allowed_deviation + 1e-6:
        return False
    if _max_distance_to_polyline(dense_curve, output) > geometry_tolerance_px * 1.05 + 1e-6:
        return False
    if closed:
        if not np.allclose(output[0], output[-1], atol=1e-7):
            return False
        if float(np.linalg.norm(output[0] - output[-1])) > allowed_deviation:
            return False
    else:
        if float(np.linalg.norm(output[0] - original[0])) > 1e-7:
            return False
        if float(np.linalg.norm(output[-1] - original[-1])) > 1e-7:
            return False
    if any(_max_distance_to_polyline(source_body[index : index + 1], output) > 1e-6 for index in anchors):
        return False
    original_length = _path_length(original)
    output_length = _path_length(output)
    if original_length <= 1e-9 or not 0.50 * original_length <= output_length <= 1.50 * original_length:
        return False
    padding = allowed_deviation + 1e-6
    if np.any(np.min(dense_curve, axis=0) < np.min(original, axis=0) - padding):
        return False
    if np.any(np.max(dense_curve, axis=0) > np.max(original, axis=0) + padding):
        return False
    if _has_proper_self_intersection(output, closed):
        if not allow_existing_self_intersections and not _has_proper_self_intersection(original, closed):
            return False
    return True


def _data_url(mask: np.ndarray) -> str:
    """把二值图或骨架图编码为前端可直接显示的 PNG data URL。"""

    diagnostic = np.where(mask, 0, 255).astype(np.uint8)
    ok, encoded = cv2.imencode(".png", diagnostic)
    if not ok:
        raise RuntimeError("Could not encode diagnostic image")
    return "data:image/png;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")


def _canonical_points(points: list[tuple[float, float]], closed: bool) -> list[tuple[float, float]]:
    """统一闭环起点和方向，避免遍历方向不同导致几何 ID 改变。"""

    if closed:
        body = points[:-1] if points[0] == points[-1] else points
        start = min(range(len(body)), key=lambda index: body[index])
        forward = body[start:] + body[:start]
        reversed_body = list(reversed(body))
        reverse_start = min(range(len(reversed_body)), key=lambda index: reversed_body[index])
        backward = reversed_body[reverse_start:] + reversed_body[:reverse_start]
        selected = min(forward, backward)
        return selected + [selected[0]]
    return points if points[0] <= points[-1] else list(reversed(points))


def _sample_audit_stroke(
    stroke: AuditStroke,
    millimeters_per_normalized_unit: float,
    spacing_mm: float,
) -> tuple[np.ndarray, np.ndarray]:
    """沿审核笔触按弧长生成近重复检测样点和单位切线。"""

    points = np.asarray(stroke.points, dtype=np.float64) * millimeters_per_normalized_unit
    sampled: list[np.ndarray] = []
    tangents: list[np.ndarray] = []
    for start, end in zip(points, points[1:]):
        vector = end - start
        length = float(np.linalg.norm(vector))
        if length <= 1e-9:
            continue
        count = max(1, math.ceil(length / spacing_mm))
        tangent = vector / length
        for index in range(count):
            position = (index + 0.5) / count
            sampled.append(start + position * vector)
            tangents.append(tangent)
    return np.asarray(sampled), np.asarray(tangents)


def _outer_contour_distance_map(
    line_mask: np.ndarray,
    mm_per_pixel: float,
) -> np.ndarray:
    """生成每个像素到显著外边界的距离图。

    只使用 ``RETR_EXTERNAL`` 的显著连通轮廓，小眼睛、衣服纹理等封闭内部
    细节不会被当作主体外轮廓。对于完全开放、找不到有效包围面积的线稿，
    使用所有线像素的凸包作为保守后备，确保仍能给出一组可画的外形候选。
    """

    mask = (np.asarray(line_mask) > 0).astype(np.uint8) * 255
    if not np.any(mask):
        return np.full(mask.shape, np.inf, dtype=np.float32)

    close_radius = int(np.clip(round(0.35 / max(mm_per_pixel, 1e-6)), 1, 5))
    kernel_size = close_radius * 2 + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _hierarchy = cv2.findContours(
        closed,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_NONE,
    )
    areas = [abs(float(cv2.contourArea(contour))) for contour in contours]
    max_area = max(areas, default=0.0)
    minimum_area = max(16.0, max_area * 0.05)
    significant = [
        contour
        for contour, area in zip(contours, areas)
        if area >= minimum_area
    ]

    boundary = np.zeros(mask.shape, dtype=np.uint8)
    if significant and max_area >= 16.0:
        cv2.drawContours(boundary, significant, -1, 1, 1)
    else:
        rows, columns = np.nonzero(mask)
        xy = np.column_stack((columns, rows)).astype(np.int32)
        if len(xy) >= 3:
            hull = cv2.convexHull(xy)
            cv2.drawContours(boundary, [hull], -1, 1, 1)
        else:
            boundary[rows, columns] = 1

    return cv2.distanceTransform(1 - boundary, cv2.DIST_L2, 3)


def _outline_likelihood(
    raw_points: np.ndarray,
    contour_distance: np.ndarray,
    tolerance_px: float,
) -> float:
    """计算一条骨架路径有多少弧长贴近显著外边界。"""

    if len(raw_points) == 0 or contour_distance.size == 0:
        return 0.0
    height, width = contour_distance.shape
    xy = np.clip(
        np.rint(raw_points).astype(np.int32),
        [0, 0],
        [width - 1, height - 1],
    )
    distances = contour_distance[xy[:, 1], xy[:, 0]]
    return float(np.clip(np.mean(distances <= tolerance_px), 0.0, 1.0))


def _prepare_color_sampling_image(rgb_image: np.ndarray) -> np.ndarray:
    """一次性生成供所有笔触复用的平滑 Lab 原图。"""

    image = np.asarray(rgb_image, dtype=np.uint8)
    smoothed = cv2.GaussianBlur(image[:, :, :3], (5, 5), 0)
    return cv2.cvtColor(smoothed, cv2.COLOR_RGB2LAB).astype(np.float32)


def _two_sided_color_contrast(
    raw_points: np.ndarray,
    lab_image: np.ndarray,
    sample_offset_px: float,
) -> float:
    """估计笔触法向两侧是否属于不同颜色区域。

    先轻微模糊以消除 JPEG 噪点和单像素锯齿，再在每个路径点的局部法线
    两侧、两个距离上取 Lab 颜色。内部墨线若两侧都是同一块肤色/衣服颜色，
    即使墨线本身很黑也会得到接近零的分数；真正的物体边界则会较高。
    """

    points = np.asarray(raw_points, dtype=np.float32)
    lab = np.asarray(lab_image, dtype=np.float32)
    if len(points) < 2 or lab.ndim != 3 or lab.shape[2] < 3:
        return 0.0
    tangents = np.empty_like(points)
    tangents[0] = points[1] - points[0]
    tangents[-1] = points[-1] - points[-2]
    if len(points) > 2:
        tangents[1:-1] = points[2:] - points[:-2]
    lengths = np.linalg.norm(tangents, axis=1)
    valid_tangent = lengths > 1e-6
    normals = np.zeros_like(points)
    normals[valid_tangent, 0] = -tangents[valid_tangent, 1] / lengths[valid_tangent]
    normals[valid_tangent, 1] = tangents[valid_tangent, 0] / lengths[valid_tangent]

    height, width = lab.shape[:2]
    strongest = np.zeros(len(points), dtype=np.float32)
    any_valid = np.zeros(len(points), dtype=bool)
    for radius in (sample_offset_px, sample_offset_px * 1.75):
        plus = points + normals * radius
        minus = points - normals * radius
        valid = (
            valid_tangent
            & (plus[:, 0] >= 0) & (plus[:, 0] <= width - 1)
            & (plus[:, 1] >= 0) & (plus[:, 1] <= height - 1)
            & (minus[:, 0] >= 0) & (minus[:, 0] <= width - 1)
            & (minus[:, 1] >= 0) & (minus[:, 1] <= height - 1)
        )
        if not np.any(valid):
            continue
        plus_color = cv2.remap(
            lab,
            plus[:, 0].reshape(-1, 1),
            plus[:, 1].reshape(-1, 1),
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )[:, 0]
        minus_color = cv2.remap(
            lab,
            minus[:, 0].reshape(-1, 1),
            minus[:, 1].reshape(-1, 1),
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )[:, 0]
        delta = np.linalg.norm(plus_color - minus_color, axis=1)
        strongest[valid] = np.maximum(strongest[valid], delta[valid])
        any_valid |= valid
    if not np.any(any_valid):
        return 0.0
    # OpenCV 8-bit Lab 中，<=10 可视为极近色；到 35 逐渐视为清晰分界。
    separated = np.clip((strongest[any_valid] - 10.0) / 25.0, 0.0, 1.0)
    return float(np.mean(separated))


def _mark_outer_contour_candidates(
    strokes: list[AuditStroke],
    parameters: ProcessingParameters,
    *,
    require_color_separation: bool = False,
) -> None:
    """标出相对最外层的一组可绘制笔触，但不改动默认审核决定。"""

    eligible = [
        stroke
        for stroke in strokes
        if stroke.length_mm >= max(1.0, parameters.pen_width_mm * 2.0)
        and "pruned_spur" not in stroke.reasons
        and stroke.scores.outline_likelihood > 0
        and (not require_color_separation or stroke.scores.color_contrast >= 0.15)
    ]
    if not eligible:
        return
    best = max(stroke.scores.outline_likelihood for stroke in eligible)
    # 相对阈值让开放线稿也至少有一组候选；绝对阈值防止内部线普遍入选。
    cutoff = max(0.35, best * 0.70)
    selected = [
        stroke for stroke in eligible
        if stroke.scores.outline_likelihood >= cutoff
    ]
    if not selected:
        selected = [max(eligible, key=lambda stroke: (stroke.scores.outline_likelihood, stroke.length_mm))]
    for stroke in selected:
        if "outer_contour_candidate" not in stroke.reasons:
            stroke.reasons.append("outer_contour_candidate")


def _mark_near_duplicate_strokes(
    strokes: list[AuditStroke],
    canvas: CanvasSpec,
    parameters: ProcessingParameters,
) -> None:
    """把几乎覆盖同一路径的冗余笔触标为可恢复 ``uncertain``。

    插画/边缘模型有时会沿同一墨线生成相邻的双边轮廓。这里不做危险的几何
    合并，也不自动永久删除：只有当一条候选至少 75% 的弧长在一个笔宽/有效
    分辨率内、切线差不超过 12°，且重合长度足够长时，才把较冗余的一条标为
    ``near_duplicate_parallel``。局部接近、交叉线以及相距超过系统可分辨尺度的
    真实双线不会触发；用户仍可在 audit/审核界面恢复。
    """

    eligible = [
        (index, stroke)
        for index, stroke in enumerate(strokes)
        if stroke.decision == Decision.KEEP and stroke.length_mm >= 2.0
    ]
    if len(eligible) < 2:
        return
    distance_mm = min(
        2.0,
        max(parameters.pen_width_mm, parameters.effective_resolution_mm),
    )
    if distance_mm <= 0:
        return
    spacing_mm = max(0.20, distance_mm * 0.5)
    millimeters_per_unit = canvas.target_width_mm / canvas.width
    all_points: list[np.ndarray] = []
    all_tangents: list[np.ndarray] = []
    owners: list[int] = []
    local_samples: dict[int, int] = {}
    for stroke_index, stroke in eligible:
        points, tangents = _sample_audit_stroke(
            stroke,
            millimeters_per_unit,
            spacing_mm,
        )
        if len(points) == 0:
            continue
        all_points.extend(points)
        all_tangents.extend(tangents)
        owners.extend([stroke_index] * len(points))
        local_samples[stroke_index] = len(points)
    if len(all_points) < 2:
        return

    point_array = np.asarray(all_points, dtype=np.float64)
    tangent_array = np.asarray(all_tangents, dtype=np.float64)
    owner_array = np.asarray(owners, dtype=np.int32)
    tree = cKDTree(point_array)
    minimum_dot = math.cos(math.radians(12.0))
    directed_counts: dict[tuple[int, int], int] = {}
    directed_distances: dict[tuple[int, int], list[float]] = {}
    neighbor_count = min(16, len(point_array))
    neighbor_distances, neighbor_indices = tree.query(
        point_array,
        k=neighbor_count,
        distance_upper_bound=distance_mm,
        workers=1,
    )
    if neighbor_count == 1:
        neighbor_distances = neighbor_distances[:, None]
        neighbor_indices = neighbor_indices[:, None]
    # Select the nearest direction-compatible sample owned by another stroke in
    # vectorized NumPy. A Python loop over every sample × every neighbour made
    # dense illustrations spend several seconds in duplicate detection.
    finite_neighbors = neighbor_indices < len(point_array)
    safe_indices = np.where(finite_neighbors, neighbor_indices, 0)
    neighbor_owners = owner_array[safe_indices]
    different_owner = neighbor_owners != owner_array[:, None]
    alignments = np.abs(
        np.sum(tangent_array[:, None, :] * tangent_array[safe_indices], axis=2)
    )
    valid = (
        finite_neighbors
        & np.isfinite(neighbor_distances)
        & different_owner
        & (alignments >= minimum_dot)
    )
    rows = np.flatnonzero(np.any(valid, axis=1))
    first_valid = np.argmax(valid[rows], axis=1)
    selected_neighbors = safe_indices[rows, first_valid]
    selected_distances = neighbor_distances[rows, first_valid]
    for source, target, distance in zip(
        owner_array[rows],
        owner_array[selected_neighbors],
        selected_distances,
    ):
        key = (int(source), int(target))
        directed_counts[key] = directed_counts.get(key, 0) + 1
        directed_distances.setdefault(key, []).append(float(distance))

    minimum_overlap_mm = max(3.0, distance_mm * 8.0)
    pair_candidates: list[tuple[float, float, int, int]] = []
    handled_pairs: set[tuple[int, int]] = set()
    for source, target in sorted(directed_counts):
        pair = tuple(sorted((source, target)))
        if pair in handled_pairs:
            continue
        handled_pairs.add(pair)
        first, second = pair
        first_coverage = directed_counts.get((first, second), 0) / max(
            local_samples.get(first, 1), 1
        )
        second_coverage = directed_counts.get((second, first), 0) / max(
            local_samples.get(second, 1), 1
        )
        first_overlap = first_coverage * strokes[first].length_mm
        second_overlap = second_coverage * strokes[second].length_mm
        qualifying: list[int] = []
        if first_coverage >= 0.75 and first_overlap >= minimum_overlap_mm:
            qualifying.append(first)
        if second_coverage >= 0.75 and second_overlap >= minimum_overlap_mm:
            qualifying.append(second)
        if not qualifying:
            continue
        if len(qualifying) == 1:
            redundant = qualifying[0]
            keeper = second if redundant == first else first
            coverage = first_coverage if redundant == first else second_coverage
        else:
            # Preserve the more complete/high-confidence path. All tie breaks use
            # stable geometry metadata, never traversal or hash-map insertion order.
            keeper = max(
                qualifying,
                key=lambda index: (
                    strokes[index].length_mm,
                    strokes[index].confidence,
                    -index,
                ),
            )
            redundant = second if keeper == first else first
            coverage = first_coverage if redundant == first else second_coverage
        distances = directed_distances.get((redundant, keeper), [distance_mm])
        pair_candidates.append(
            (-coverage, float(np.median(distances)), redundant, keeper)
        )

    marked: set[int] = set()
    for _negative_coverage, _distance, redundant, keeper in sorted(pair_candidates):
        if redundant in marked or keeper in marked:
            continue
        stroke = strokes[redundant]
        if stroke.decision != Decision.KEEP:
            continue
        stroke.decision = Decision.UNCERTAIN
        if "near_duplicate_parallel" not in stroke.reasons:
            stroke.reasons.append("near_duplicate_parallel")
        stroke.scores.risk = max(stroke.scores.risk, 0.5)
        marked.add(redundant)


def _component_scale_scores(
    strokes: list[AuditStroke],
    millimeters_per_unit: float,
    link_distance_mm: float,
    canvas_diagonal_mm: float,
) -> list[float]:
    """Estimate the physical scale of the connected structure owning each stroke."""

    count = len(strokes)
    parents = list(range(count))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parents[max(first_root, second_root)] = min(first_root, second_root)

    cell = max(link_distance_mm, 1e-6)
    buckets: dict[tuple[int, int], list[tuple[int, np.ndarray]]] = {}
    for index, stroke in enumerate(strokes):
        points = np.asarray(stroke.points, dtype=np.float64) * millimeters_per_unit
        for endpoint in (points[0], points[-1]):
            key = (int(math.floor(endpoint[0] / cell)), int(math.floor(endpoint[1] / cell)))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for other_index, other_endpoint in buckets.get((key[0] + dx, key[1] + dy), []):
                        if other_index != index and float(np.linalg.norm(endpoint - other_endpoint)) <= cell:
                            union(index, other_index)
            buckets.setdefault(key, []).append((index, endpoint))

    bounds: dict[int, list[float]] = {}
    for index, stroke in enumerate(strokes):
        root = find(index)
        points = np.asarray(stroke.points, dtype=np.float64) * millimeters_per_unit
        minimum = np.min(points, axis=0)
        maximum = np.max(points, axis=0)
        if root not in bounds:
            bounds[root] = [minimum[0], minimum[1], maximum[0], maximum[1]]
        else:
            bound = bounds[root]
            bound[0] = min(bound[0], minimum[0])
            bound[1] = min(bound[1], minimum[1])
            bound[2] = max(bound[2], maximum[0])
            bound[3] = max(bound[3], maximum[1])
    return [
        float(np.clip(
            math.hypot(
                bounds[find(index)][2] - bounds[find(index)][0],
                bounds[find(index)][3] - bounds[find(index)][1],
            ) / max(canvas_diagonal_mm, 1e-9),
            0.0,
            1.0,
        ))
        for index in range(count)
    ]


def _stroke_footprint(
    stroke: AuditStroke,
    millimeters_per_unit: float,
    cell_mm: float,
    grid_width: int,
    disk_offsets: list[tuple[int, int]],
) -> set[int]:
    """Rasterize a polyline into a sparse set of physical ink-grid cells."""

    points = np.asarray(stroke.points, dtype=np.float64) * millimeters_per_unit
    footprint: set[int] = set()
    sampling_step = max(cell_mm * 0.5, 1e-6)
    for start, end in zip(points, points[1:]):
        vector = end - start
        length = float(np.linalg.norm(vector))
        sample_count = max(1, int(math.ceil(length / sampling_step)))
        for position in np.linspace(0.0, 1.0, sample_count + 1):
            point = start + vector * position
            column = int(round(point[0] / cell_mm))
            row = int(round(point[1] / cell_mm))
            for offset_x, offset_y in disk_offsets:
                candidate_column = column + offset_x
                candidate_row = row + offset_y
                if candidate_column >= 0 and candidate_row >= 0:
                    footprint.add(candidate_row * grid_width + candidate_column)
    return footprint


def _physical_importance_selection(
    strokes: list[AuditStroke],
    canvas: CanvasSpec,
    parameters: ProcessingParameters,
) -> StrokeSelectionSummary:
    """Rank raster strokes by structure and sparse physical ink contribution."""

    detail = parameters.detail_level / 100.0
    feature_scale_mm = max(
        parameters.minimum_length_mm,
        parameters.pen_width_mm * (2.0 - 1.5 * detail),
    )
    cell_mm = max(
        parameters.effective_resolution_mm,
        parameters.pen_width_mm / 3.0,
        max(canvas.target_width_mm, canvas.target_height_mm) / 1536.0,
    )
    millimeters_per_unit = canvas.target_width_mm / canvas.width
    canvas_diagonal = math.hypot(canvas.target_width_mm, canvas.target_height_mm)
    component_scores = _component_scale_scores(
        strokes,
        millimeters_per_unit,
        max(parameters.pen_width_mm, parameters.effective_resolution_mm),
        canvas_diagonal,
    )
    length_denominator = math.log1p(canvas_diagonal / max(feature_scale_mm, 1e-6))
    for index, stroke in enumerate(strokes):
        length_score = math.log1p(stroke.length_mm / max(feature_scale_mm, 1e-6))
        length_score = float(np.clip(length_score / max(length_denominator, 1e-9), 0.0, 1.0))
        local_importance = (
            0.45 * stroke.scores.outline_likelihood
            + 0.20 * length_score
            + 0.15 * component_scores[index]
            + 0.10 * stroke.scores.line_confidence
            + 0.10 * stroke.scores.color_contrast
        )
        if stroke.scores.model_confidence > 0:
            model_importance = (
                0.55 * stroke.scores.semantic_importance
                + 0.45 * stroke.scores.removal_damage
            )
            base_importance = (
                0.65 * model_importance
                + 0.35 * local_importance
            )
        else:
            base_importance = local_importance
        stroke.scores.importance = round(float(np.clip(base_importance, 0.0, 1.0)), 6)
        if (
            stroke.decision == Decision.KEEP
            and stroke.length_mm < feature_scale_mm
            and stroke.scores.outline_likelihood < 0.75
        ):
            stroke.decision = Decision.UNCERTAIN
            stroke.scores.risk = max(stroke.scores.risk, 0.5)
            if "below_physical_feature_scale" not in stroke.reasons:
                stroke.reasons.append("below_physical_feature_scale")

    automatic_candidates = [
        index for index, stroke in enumerate(strokes)
        if stroke.decision == Decision.KEEP
    ]
    if not automatic_candidates:
        for rank, index in enumerate(
            sorted(
                range(len(strokes)),
                key=lambda item: (-strokes[item].scores.importance, strokes[item].id),
            ),
            start=1,
        ):
            strokes[index].importance_rank = rank
        return StrokeSelectionSummary(
            requested_max_strokes=parameters.max_strokes,
            candidate_count=len(strokes),
            footprint_cell_mm=round(cell_mm, 6),
            physical_feature_scale_mm=round(feature_scale_mm, 6),
        )

    grid_width = int(math.ceil(canvas.target_width_mm / cell_mm)) + 3
    radius_cells = max(0, int(math.ceil((parameters.pen_width_mm / 2.0) / cell_mm)))
    disk_offsets = [
        (offset_x, offset_y)
        for offset_x in range(-radius_cells, radius_cells + 1)
        for offset_y in range(-radius_cells, radius_cells + 1)
        if radius_cells == 0
        or math.hypot(offset_x, offset_y) <= radius_cells + 0.25
    ]
    footprints = {
        index: _stroke_footprint(
            strokes[index],
            millimeters_per_unit,
            cell_mm,
            grid_width,
            disk_offsets,
        )
        for index in automatic_candidates
    }
    total_cell_weights: dict[int, float] = {}
    for index in automatic_candidates:
        weight = max(strokes[index].scores.importance, 0.01)
        for cell_id in footprints[index]:
            total_cell_weights[cell_id] = max(total_cell_weights.get(cell_id, 0.0), weight)
    total_weight = sum(total_cell_weights.values())

    current_cell_weights: dict[int, float] = {}
    heap: list[tuple[float, str, int]] = [
        (-(0.75 * strokes[index].scores.importance + 0.25), strokes[index].id, index)
        for index in automatic_candidates
    ]
    heapq.heapify(heap)
    useful_order: list[int] = []
    cumulative_coverages: list[float] = []
    redundant: list[int] = []
    redundancy_threshold = 0.55 - 0.45 * detail
    covered_weight = 0.0
    while heap:
        _upper, _stroke_id, index = heapq.heappop(heap)
        footprint = footprints[index]
        weight = max(strokes[index].scores.importance, 0.01)
        gain = sum(
            max(0.0, weight - current_cell_weights.get(cell_id, 0.0))
            for cell_id in footprint
        )
        weighted_fraction = gain / max(weight * len(footprint), 1e-9)
        priority = 0.75 * strokes[index].scores.importance + 0.25 * weighted_fraction
        if heap and priority + 1e-12 < -heap[0][0]:
            heapq.heappush(heap, (-priority, strokes[index].id, index))
            continue
        new_cells = sum(1 for cell_id in footprint if cell_id not in current_cell_weights)
        marginal_fraction = new_cells / max(len(footprint), 1)
        strokes[index].scores.marginal_coverage = round(marginal_fraction, 6)
        if (
            marginal_fraction < redundancy_threshold
            and strokes[index].scores.importance < 0.75
        ):
            redundant.append(index)
            strokes[index].decision = Decision.UNCERTAIN
            strokes[index].scores.risk = max(strokes[index].scores.risk, 0.5)
            if "pen_footprint_redundant" not in strokes[index].reasons:
                strokes[index].reasons.append("pen_footprint_redundant")
            continue
        useful_order.append(index)
        for cell_id in footprint:
            previous_weight = current_cell_weights.get(cell_id, 0.0)
            next_weight = max(previous_weight, weight)
            current_cell_weights[cell_id] = next_weight
            covered_weight += next_weight - previous_weight
        cumulative_coverages.append(covered_weight / max(total_weight, 1e-9))

    recommended = next(
        (
            position
            for position, coverage in enumerate(cumulative_coverages, start=1)
            if coverage >= 0.85
        ),
        len(useful_order),
    )
    target_coverage = 0.75 + 0.20 * detail
    selected: list[int] = []
    achieved_coverage = 0.0
    for position, index in enumerate(useful_order):
        if len(selected) >= parameters.max_strokes:
            strokes[index].decision = Decision.UNCERTAIN
            if "max_strokes_excluded" not in strokes[index].reasons:
                strokes[index].reasons.append("max_strokes_excluded")
            continue
        if selected and achieved_coverage >= target_coverage:
            strokes[index].decision = Decision.UNCERTAIN
            if "detail_budget_excluded" not in strokes[index].reasons:
                strokes[index].reasons.append("detail_budget_excluded")
            continue
        selected.append(index)
        achieved_coverage = cumulative_coverages[position]

    useful_set = set(useful_order)
    redundant_set = set(redundant)
    trailing = [
        index for index in range(len(strokes))
        if index not in useful_set and index not in redundant_set
    ]
    complete_order = useful_order + sorted(
        redundant + trailing,
        key=lambda item: (-strokes[item].scores.importance, strokes[item].id),
    )
    for rank, index in enumerate(complete_order, start=1):
        strokes[index].importance_rank = rank

    return StrokeSelectionSummary(
        recommended_min_strokes=recommended,
        requested_max_strokes=parameters.max_strokes,
        candidate_count=len(strokes),
        automatic_keep_count=len(selected),
        target_coverage=round(target_coverage, 6),
        achieved_coverage=round(float(achieved_coverage), 6),
        footprint_cell_mm=round(cell_mm, 6),
        physical_feature_scale_mm=round(feature_scale_mm, 6),
    )


def process_classic(
    content: bytes,
    filename: str,
    parameters: ProcessingParameters,
    *,
    line_mask: np.ndarray | None = None,
    confidence_map: np.ndarray | None = None,
    actual_provider: str = "classic",
    identity_salt: str = "",
) -> ProcessResponse:
    """执行完整栅格图片转笔触流程，返回正式数据、审核数据和诊断图。

    line_mask/confidence_map 为空时使用本文件的经典 OpenCV 提取器；传入
    它们则说明 Lineart/PiDiNet/HED 已生成线稿，本函数从骨架化继续处理。
    这个复用入口是“线稿模型可替换、下游几何契约不变”的关键边界。
    """

    # 输入哈希参与笔触 ID 和 processing_id，保证相同输入参数结果稳定。
    source_hash = hashlib.sha256(content).hexdigest()
    identity_hash = (
        hashlib.sha256(f"{source_hash}:{identity_salt}".encode()).hexdigest()
        if identity_salt
        else source_hash
    )
    decoded, source_width, source_height = decode_raster(
        content,
        _processing_max_dimension(parameters.detail_level),
    )
    image = _resize_for_processing(decoded, parameters.detail_level)
    if line_mask is None or confidence_map is None:
        line_mask, confidence_map = extract_classic_lineart(image, parameters)
    elif line_mask.shape != image.shape[:2]:
        line_mask = cv2.resize(
            line_mask.astype(np.uint8),
            (image.shape[1], image.shape[0]),
            interpolation=cv2.INTER_NEAREST,
        ) > 0
        confidence_map = cv2.resize(
            confidence_map.astype(np.float32),
            (image.shape[1], image.shape[0]),
            interpolation=cv2.INTER_LINEAR,
        )

    # 统一几何处理链：线条区域 -> 单像素中心线 -> 分支 -> 连续笔触。
    skeleton = skeletonize_mask(line_mask)
    process_height, process_width = skeleton.shape
    physical_layout = fit_canvas_layout(
        process_width,
        process_height,
        parameters,
        source_width=source_width,
        source_height=source_height,
    )
    mm_per_pixel = physical_layout.millimeters_per_source_unit
    traced = trace_skeleton(
        skeleton,
        mm_per_pixel=mm_per_pixel,
        confidence_map=confidence_map,
        parameters=parameters,
        line_mask=line_mask,
    )
    canvas = physical_layout.canvas
    contour_distance = _outer_contour_distance_map(line_mask, mm_per_pixel)
    outline_tolerance_px = float(np.clip(
        parameters.pen_width_mm / max(mm_per_pixel, 1e-6) + 2.0,
        3.0,
        12.0,
    ))
    # “经典 OpenCV（线稿/扫描稿）”没有可靠的原始色块，只有该模式跳过
    # 两侧颜色门槛；插画、照片、HED 和千问均以用户上传的原图判断。
    require_outline_color = parameters.provider != "classic"
    color_sampling_image = (
        _prepare_color_sampling_image(image) if require_outline_color else None
    )
    color_sample_offset_px = float(np.clip(
        parameters.pen_width_mm / max(mm_per_pixel, 1e-6) + 2.0,
        2.0,
        8.0,
    ))
    audit_strokes: list[AuditStroke] = []
    for candidate_order, traced_path in enumerate(traced, start=1):
        raw_points = traced_path.points
        closed = traced_path.closed
        # 每条骨架路径独立简化、平滑，再映射到统一坐标空间。
        processed_points = _smooth_and_simplify(
            raw_points,
            closed,
            parameters,
            mm_per_pixel,
        )
        if len(processed_points) < 2:
            continue
        normalized = [
            tuple(round(value, 6) for value in physical_layout.normalize_source_point(float(x), float(y)))
            for x, y in processed_points
        ]
        normalized = _canonical_points(normalized, closed)
        # 由目标绘图宽度换算毫米长度，使审核阈值不依赖原图分辨率。
        pixel_length = sum(
            math.dist(processed_points[index - 1], processed_points[index])
            for index in range(1, len(processed_points))
        )
        length_mm = pixel_length * mm_per_pixel
        sample_xy = np.clip(np.rint(raw_points).astype(int), [0, 0], [process_width - 1, process_height - 1])
        confidence = float(np.mean(confidence_map[sample_xy[:, 1], sample_xy[:, 0]]))
        spatial_outline_likelihood = _outline_likelihood(
            raw_points,
            contour_distance,
            outline_tolerance_px,
        )
        color_contrast = (
            _two_sided_color_contrast(raw_points, color_sampling_image, color_sample_offset_px)
            if require_outline_color
            else 1.0
        )
        outline_likelihood = (
            spatial_outline_likelihood * color_contrast
            if require_outline_color
            else spatial_outline_likelihood
        )
        # 以下风险评分是项目自定义规则，不是 OpenCV/Skan 的内置判断。
        # discard 仍保存在 audit.json，用户可以在审核界面恢复。
        shortness = max(0.0, 1 - length_mm / max(parameters.minimum_length_mm, 1e-6))
        low_confidence = max(0.0, 1 - confidence)
        risk = float(np.clip(0.65 * shortness + 0.35 * low_confidence, 0, 1))
        reasons: list[str] = list(traced_path.reasons)
        if length_mm < parameters.minimum_length_mm and "pruned_spur" not in reasons:
            reasons.append("too_short_isolated")
        if confidence < 0.35:
            reasons.append("low_confidence")
        if traced_path.decision_hint == Decision.DISCARD:
            risk = max(risk, 0.75)
            decision = Decision.DISCARD
        elif traced_path.decision_hint == Decision.UNCERTAIN:
            risk = max(risk, 0.50)
            decision = Decision.UNCERTAIN
        elif length_mm < parameters.minimum_length_mm * 0.5:
            # A path below half the explicit user minimum remains clear noise.
            # Pen-footprint/detail-budget exclusions below are recoverable.
            risk = max(risk, 0.75)
            decision = Decision.DISCARD
        elif risk >= 0.4:
            decision = Decision.UNCERTAIN
        else:
            decision = Decision.KEEP
        # 使用输入哈希与规范化几何生成确定性 ID，不引入随机数。
        canonical_json = json.dumps([normalized, closed], separators=(",", ":"))
        stroke_id = "stroke_" + hashlib.sha256(
            f"{identity_hash}:{canonical_json}".encode()
        ).hexdigest()[:12]
        audit_strokes.append(
            AuditStroke(
                id=stroke_id,
                source="raster",
                source_order=candidate_order,
                points=normalized,
                closed=closed,
                confidence=round(confidence, 6),
                decision=decision,
                reasons=reasons,
                scores=AuditScores(
                    risk=round(risk, 6),
                    line_confidence=round(confidence, 6),
                    outline_likelihood=round(outline_likelihood, 6),
                    color_contrast=round(color_contrast, 6),
                ),
                length_mm=round(length_mm, 4),
            )
        )
    # 稳定排序保证同一输入与参数每次得到相同输出顺序。
    audit_strokes.sort(key=lambda stroke: (stroke.points[0][1], stroke.points[0][0], stroke.id))
    _mark_outer_contour_candidates(
        audit_strokes,
        parameters,
        require_color_separation=require_outline_color,
    )
    selection_summary = _physical_importance_selection(audit_strokes, canvas, parameters)
    audit_strokes.sort(
        key=lambda stroke: (
            stroke.importance_rank if stroke.importance_rank is not None else 10**9,
            stroke.id,
        )
    )
    kept_strokes = sorted(
        (stroke for stroke in audit_strokes if stroke.decision == Decision.KEEP),
        key=lambda stroke: (
            stroke.importance_rank if stroke.importance_rank is not None else 10**9,
            stroke.id,
        ),
    )
    # 正式 strokes.json 只包含 keep；完整状态、评分和原因留在 audit.json。
    lean = [
        DrawingStrokeGeometry(
            id=stroke.id,
            order=order,
            points=stroke.points,
            closed=stroke.closed,
        )
        for order, stroke in enumerate(kept_strokes, start=1)
    ]
    fingerprint = hashlib.sha256(
        (identity_hash + parameters.model_dump_json() + actual_provider).encode()
    ).hexdigest()[:12]
    result_warnings: list[str] = []
    if parameters.max_strokes < selection_summary.recommended_min_strokes:
        result_warnings.append(
            f"max_strokes_below_recommended:{parameters.max_strokes}:"
            f"{selection_summary.recommended_min_strokes}"
        )
    return ProcessResponse(
        processing_id=f"process_{fingerprint}",
        filename=filename,
        strokes_document=StrokesDocument(canvas=canvas, strokes=lean),
        audit_document=AuditDocument(
            canvas=canvas,
            processing=AuditProcessing(
                requested_provider=parameters.provider,
                actual_provider=actual_provider,
                parameters=parameters,
                source_sha256=source_hash,
            ),
            strokes=audit_strokes,
            warnings=result_warnings,
            selection_summary=selection_summary,
        ),
        diagnostics=DiagnosticImages(
            binary_png_data_url=_data_url(line_mask),
            skeleton_png_data_url=_data_url(skeleton),
        ),
    )


def refinalize_raster_result(result: ProcessResponse) -> ProcessResponse:
    """Reapply physical selection after semantic model scores have been added."""

    audit = result.audit_document
    parameters = audit.processing.parameters
    budget_reasons = {"detail_budget_excluded", "max_strokes_excluded"}
    for stroke in audit.strokes:
        if stroke.decision_source == "algorithm" and any(
            reason in budget_reasons for reason in stroke.reasons
        ):
            stroke.reasons = [
                reason for reason in stroke.reasons if reason not in budget_reasons
            ]
            stroke.decision = Decision.KEEP
    audit.warnings = [
        warning for warning in audit.warnings
        if not warning.startswith("max_strokes_below_recommended:")
    ]
    summary = _physical_importance_selection(audit.strokes, audit.canvas, parameters)
    audit.selection_summary = summary
    if parameters.max_strokes < summary.recommended_min_strokes:
        audit.warnings.append(
            f"max_strokes_below_recommended:{parameters.max_strokes}:"
            f"{summary.recommended_min_strokes}"
        )
    audit.strokes.sort(
        key=lambda stroke: (
            stroke.importance_rank if stroke.importance_rank is not None else 10**9,
            stroke.id,
        )
    )
    kept = [stroke for stroke in audit.strokes if stroke.decision == Decision.KEEP]
    result.strokes_document.strokes = [
        DrawingStrokeGeometry(
            id=stroke.id,
            order=order,
            points=stroke.points,
            closed=stroke.closed,
        )
        for order, stroke in enumerate(kept, start=1)
    ]
    return result
