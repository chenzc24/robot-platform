# AprilTag 平面板标定工具

## 目的与边界

`app/apriltag_board_calibration.py` 用少量已实测的锚点 Tag，离线求出同一
平面上其余 Tag 的世界四角坐标。它只读图片或 RTSP 视频，不连接 ESP32、
MaixCam 命令服务或机械臂，也不会发出任何运动命令。

这项标定建立的是 `drawing_board` 平面布局，不是相机内参、相机到机械臂
外参或小车轨道原点。输出可供现有 `localized_baseline` 位姿解算器使用，
但不会自动改写 `drawing.local.json`，并始终保持
`production_ready: false`，直到现场人员完成物理复核。

## 坐标与输入

先建立锚点文件，例如忽略版本控制的
`config/apriltag-center-anchors.local.json`。中心锚点格式只写实测中心和共同
黑框边长，不把未测量的角点方向当成已知量：

```json
{
  "schema_version": 1,
  "layout_id": "drawing-board-center-anchors-draft",
  "frame": "drawing_board",
  "units": "mm",
  "dictionary": "DICT_APRILTAG_36H11",
  "tag_size_mm": 37.5,
  "anchors": {
    "0": {"center": [0, 0, 0]},
    "1": {"center": [0, 300, 0]},
    "2": {"center": [1000, 0, 0]},
    "3": {"center": [1000, 300, 0]}
  }
}
```

约束规则是：

- 原点建议取画板左上角；
- X 沿轨道正方向，Y 沿画板向下，Z 垂直画板；
- 单位统一为毫米；
- ID0–3 的中心位置固定，但各自的平面旋转由全部观测共同拟合；
- ID4–7 的中心 X/Y 与平面旋转均自由，不强迫等距、同排或对称；
- 只固定共同黑框边长和共面性，这两项是 Tag 的物理定义；
- 四个锚点尽量分布在布局最外侧，不能集中在一小段。

厘米级测量可用于首次联调，但不能据此声称 3 mm 级定位。最终布局应把
锚点中心测到约 1–2 mm，并确认打印 Tag 的实际黑色方框边长。工具也继续
接受旧式四角锚点 board 文件，但那种输入会把四个角全部视为已测量固定值。

## 采集

小车每次完全停稳后，从 RTSP 保存 20 个带 Tag 的帧。每个位置使用不同的
`--station`，后续位置用 `--append` 追加到同一个观测文件：

```powershell
.\.venv\Scripts\python.exe app\apriltag_board_calibration.py capture `
  --source rtsp://127.0.0.1:8555/maixcam `
  --output logs\vision\board-observations.local.json `
  --station stop-01

.\.venv\Scripts\python.exe app\apriltag_board_calibration.py capture `
  --source rtsp://127.0.0.1:8555/maixcam `
  --output logs\vision\board-observations.local.json `
  --station stop-02 --append
```

采集命令只保存 ID 和像素四角。它也接受单张图片、图片目录或通配符，便于
离线复查。默认忽略最短边小于 12 px 的 Tag。

相机到 Tag 平面的距离和俯仰角不需要保持不变；不同距离和视角能增加约束。
必须保持相机型号、焦距、对焦、分辨率和裁剪方式不变。手持采集时可以在
各位置之间走动，但正式样本应取自 5–8 个短暂停留段，避开运动模糊和明显
滚动快门形变；程序用不同 `--station` 保存这些停留段。

观测必须形成从锚点到每个未知 Tag 的连续重叠链。一个可靠的八 Tag 现场
序列是：

```text
左端锚点 + 左中 Tag
左中 Tag + 右中 Tag
右中 Tag + 右端锚点
```

上下两排应尽量同时进入画面。每个未知 Tag 至少需要三帧能同时看到它和
另一个已连接 Tag；建议在 5–8 个停车位置采集，而不是只在一个位置重复帧。

## 求解

下面假设完整布局 ID 是 0–7。实际运行时必须替换为现场打印的真实 ID：

```powershell
.\.venv\Scripts\python.exe app\apriltag_board_calibration.py solve `
  --observations logs\vision\board-observations.local.json `
  --anchors config\apriltag-center-anchors.local.json `
  --target-ids 0,1,2,3,4,5,6,7 `
  --layout-id drawing-board-eight-tag-v1 `
  --output config\apriltag-board.fitted.local.json `
  --report logs\vision\apriltag-board-fit-report.local.json
```

求解器执行以下物理约束：

1. 锚点世界中心保持原值，锚点自身的平面旋转参与联合拟合；
2. 每帧用已连接 Tag 建立“像素平面 → drawing_board 平面”单应变换；
3. 未知 Tag 通过相邻重叠帧逐段接入；
4. 每个 Tag 是边长 37.5 mm 的刚性正方形，但允许独立的平面旋转；
5. 多帧结果采用稳健汇总，并报告被拒绝的离群帧；
6. 最后逐 Tag 留一交叉验证，报告世界坐标角点残差。

中心锚点文件直接提供实际黑框边长。使用旧式四角锚点文件时，工具默认取
锚点边长中位数；两种方式都可用 `--tag-size-mm` 显式覆盖。

## 结果判读与接入

报告中的主要字段是：

- `co_visible_edges`：实际观测到的 Tag 重叠图；
- `accepted_frame_count` / `rejected_frame_count`：每个未知 Tag 的有效样本；
- `accepted_station_count`：有效样本覆盖的不同停车位置数，默认至少为 2；
- `fit_sample_rmse_mm`：多帧反投影在板坐标中的一致性；
- `held_out_corner_rmse_mm`：不使用当前 Tag 建立变换时，对它的四角预测误差；
- `cross_validated_corner_rmse_mm`：全部可交叉验证角点的综合值。
- `bundle_reprojection_rmse_px`：中心锚点、自由 Tag 和逐帧单应联合拟合后的像素残差。

工具不内置虚假的统一“合格阈值”。先检查每个未知 Tag 至少覆盖多个停车
位置、残差没有随轨道位置单向增大，再用卷尺复核输出中心距与上下排间距。
若边缘残差明显大于中部，优先完成真实相机内参/畸变标定；未建模镜头畸变
不能靠增加重复帧消除。

物理复核后，将生成文件的 `apriltag_board` 内容并入
`config/drawing.local.json`，给它一个冻结的 `layout_id`，再单独决定何时把
board 与相机内参的 `production_ready` 改为 `true`。轨道参考位置
`json_origin_rail_position_mm` 和 `json_mm_per_rail_mm` 仍按已知距离移动另行
标定，不属于本工具输出。
