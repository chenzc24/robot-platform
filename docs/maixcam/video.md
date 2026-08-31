# MaixCam视频通信

## 1. 当前边界

本阶段只建立MaixCam到电脑的视频链路，不实现统一控制台、视觉识别、ESP32通信或机械臂控制。

```text
MaixCam GC4653
  └─ NV21采集 / H.264编码
      └─ RTSP :8554/live
          ├─ PyAV直接探测和抓帧
          └─ FFmpeg -c:v copy（电脑，仅解包/重封装）
              └─ MediaMTX（电脑）
                  ├─ RTSP 127.0.0.1:8555/maixcam
                  ├─ HLS  http://127.0.0.1:8888/maixcam/index.m3u8
                  └─ WebRTC http://127.0.0.1:8889/maixcam/
```

MaixVision和MaixCode不属于该链路。SSH/SCP只负责代码部署、进程启停和日志，不承载持续视频。

## 2. 默认媒体参数

- 分辨率：1280×720。
- 编码：H.264。
- 目标帧率：20 fps。
- 目标码率：2 Mbps。
- 设备RTSP端口：8554。
- 路径：`/live`。
- RTSP接收优先使用TCP，避免Windows防火墙阻断RTP/UDP回包。

MaixPy RTSP要求摄像头使用NV21，即 `image.Format.FMT_YVU420SP`。视频进程导入MaixPy后立即调用 `comm.rm_default_comm_listener()`，释放系统默认UART0协议监听器；视频代码不读写任何机器人业务串口。

## 3. 日常操作

在VS Code中运行以下任务：

1. MaixCam重启后先在设备屏幕退出自启动的 `num` 应用；它与RTSP服务不能同时占用摄像头。
2. `MaixCam Video: Start RTSP`：上传并启动设备RTSP服务。
3. `MaixCam Video: Probe direct`：直接接收10秒并保存 `tmp/maixcam-frame.png`。
4. `MaixCam Video: Start PC relay`：启动电脑侧FFmpeg兼容桥和MediaMTX转发服务。
5. `MaixCam Video: Probe relay`：通过本机RTSP转发再次接收和抓帧。
6. `MaixCam Video: Open WebRTC`：在浏览器打开MediaMTX自带的WebRTC播放页。
7. `MaixCam Video: Stop RTSP` 和 `Stop PC relay`：停止对应进程。

命令行等价操作：

```powershell
ssh robot-maixcam /root/robot-platform/video/start.sh
.venv\Scripts\python.exe tools\maixcam\rtsp_probe.py --seconds 10
tools\maixcam\mediamtx.ps1 -Action start
.venv\Scripts\python.exe tools\maixcam\rtsp_probe.py --url rtsp://127.0.0.1:8555/maixcam --seconds 10
```

探针会把mDNS名称显式解析为IPv4。当前热点同时发布了不可达的设备IPv6地址，直接让FFmpeg/PyAV自行选择可能造成长时间等待；不要把当前DHCP IPv4提交到仓库。

## 4. 电脑侧兼容桥与MediaMTX

当前电脑使用MediaMTX v1.20.0和FFmpeg 9.0.1 Windows amd64，放在Git忽略目录：

```text
.tools/mediamtx-v1.20.0/
.tools/ffmpeg-9.0.1/
```

两个发布包的SHA256均已与发布方校验值匹配。MaixCam的RTSP会话声明H.264 packetization mode 0，但实际包含FU-A分片；MediaMTX直接拉取时会显示路径就绪但收不到媒体字节。因此FFmpeg先以 `-c:v copy` 解包并重新封装，再作为publisher推给MediaMTX。该过程不解码、不重新编码，不改变分辨率和目标码率。

可提交模板为 `config/mediamtx.example.yml`；实际 `config/mediamtx.local.yml` 被Git忽略。启动包装器每次从 `maixcam-6c7d.local` 查询当前IPv4，但不把DHCP地址写入配置或仓库。MediaMTX的 `maixcam` 路径只接受本机FFmpeg publisher。

新电脑安装时，从 [MediaMTX Releases](https://github.com/bluenviron/mediamtx/releases) 下载 v1.20.0 Windows amd64，并从 [FFmpeg官方下载页](https://ffmpeg.org/download.html) 选择Windows amd64发布包。校验发布方SHA256后解压到上述目录，再创建本地配置：

```powershell
Copy-Item config\mediamtx.example.yml config\mediamtx.local.yml
```

`tools/maixcam/mediamtx.ps1` 只负责解析当前设备IPv4、按顺序启停两个成熟工具、记录PID和日志，不实现媒体协议或编解码。

配置仅监听电脑回环地址，关闭未使用的RTMP、SRT和MoQ入口。未来需要其它电脑观看时，应另建网络与认证目标，不能直接把端口暴露到不受控网络。

## 5. 已验证的输出

| 端点 | 本轮验证 |
|---|---|
| MaixCam RTSP `rtsp://maixcam-6c7d.local:8554/live` | PyAV解码与实际抓帧通过 |
| 本机RTSP `rtsp://127.0.0.1:8555/maixcam` | 重启后连续30秒解码592帧，1280×720、20 fps |
| HLS `http://127.0.0.1:8888/maixcam/index.m3u8` | HTTP 200且FFmpeg解码通过 |
| WebRTC `http://127.0.0.1:8889/maixcam/` | 播放页HTTP 200，用户已确认实际视频流正常 |

用户验收时确认画面需要顺时针旋转90°。该需求已记录，但本视频通信目标不修改原始编码流；旋转将在后续显示和视觉坐标系目标中统一实施。

## 6. 停止与恢复

- 本目标不设置设备自启动；MaixCam重启后视频服务默认不运行。
- 设备确认/返回键可能终止当前MaixPy视频进程。
- 使用 `stop.sh` 正常释放摄像头后，当前多媒体驱动存在同一系统会话内再次初始化失败的风险；如果日志出现 `No buffer space available` 或卡在ISP初始化，应停止残留进程并物理重启设备。
- 强制终止进程前先尝试 `stop.sh`；不得同时运行两个摄像头应用。
- `Stop PC relay` 先停FFmpeg，再停MediaMTX；不影响MaixCam原生RTSP服务。

## 7. 尚未包含

- 已确认的顺时针90°显示旋转，以及畸变、曝光和颜色标定。
- 检测框、目标坐标和识别结果叠加。
- 浏览器控制台布局及设备控制。
- 自动启动、守护、健康检查和断线恢复策略。
- 录像、循环存储与数据保留策略。

这些内容分别建立后续目标；视频不得作为机器人安全状态的唯一反馈。
