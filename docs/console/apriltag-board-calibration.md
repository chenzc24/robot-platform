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
`config/apriltag-board.anchors.local.json`。格式与现有 board schema 相同，
只包含四个已测锚点：

- 原点建议取画板左上角；
- X 沿轨道正方向，Y 沿画板向下，Z 垂直画板；
- 单位统一为毫米；
- 每个 Tag 必须填写四个实测角点，而不只是中心点；
- 角点顺序固定为解码后的左上、右上、右下、左下；
- 四个锚点尽量分布在布局最外侧，不能集中在一小段。

厘米级测量可用于首次联调，但不能据此声称 3 mm 级定位。最终布局应把
锚点四角测到约 1–2 mm，并先确认打印 Tag 的实际黑色方框边长。

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
  --anchors config\apriltag-board.anchors.local.json `
  --target-ids 0,1,2,3,4,5,6,7 `
  --layout-id drawing-board-eight-tag-v1 `
  --output config\apriltag-board.fitted.local.json `
  --report logs\vision\apriltag-board-fit-report.local.json
```

求解器执行以下物理约束：

1. 锚点世界四角保持原值，不参与优化；
2. 每帧用已连接 Tag 建立“像素平面 → drawing_board 平面”单应变换；
3. 未知 Tag 通过相邻重叠帧逐段接入；
4. 每个未知 Tag 被约束为与锚点同尺寸的刚性正方形，但允许独立的平面旋转；
5. 多帧结果采用稳健汇总，并报告被拒绝的离群帧；
6. 最后逐 Tag 留一交叉验证，报告世界坐标角点残差。

如所有 Tag 的实际边长相同，工具默认使用锚点边长中位数。也可用
`--tag-size-mm` 显式指定实测边长。

## 结果判读与接入

报告中的主要字段是：

- `co_visible_edges`：实际观测到的 Tag 重叠图；
- `accepted_frame_count` / `rejected_frame_count`：每个未知 Tag 的有效样本；
- `accepted_station_count`：有效样本覆盖的不同停车位置数，默认至少为 2；
- `fit_sample_rmse_mm`：多帧反投影在板坐标中的一致性；
- `held_out_corner_rmse_mm`：不使用当前 Tag 建立变换时，对它的四角预测误差；
- `cross_validated_corner_rmse_mm`：全部可交叉验证角点的综合值。

工具不内置虚假的统一“合格阈值”。先检查每个未知 Tag 至少覆盖多个停车
位置、残差没有随轨道位置单向增大，再用卷尺复核输出中心距与上下排间距。
若边缘残差明显大于中部，优先完成真实相机内参/畸变标定；未建模镜头畸变
不能靠增加重复帧消除。

物理复核后，将生成文件的 `apriltag_board` 内容并入
`config/drawing.local.json`，给它一个冻结的 `layout_id`，再单独决定何时把
board 与相机内参的 `production_ready` 改为 `true`。轨道参考位置
`json_origin_rail_position_mm` 和 `json_mm_per_rail_mm` 仍按已知距离移动另行
标定，不属于本工具输出。
