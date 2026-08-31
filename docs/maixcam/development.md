# MaixCam开发环境

- 设备：MaixCam Pro
- 设备名：`maixcam-6c7d.local`
- 系统：Buildroot 2023.11.2，Linux 5.10.4，`riscv64`
- Python：3.11.6
- MaixPy API：4.12.5
- 开发网络：电脑和设备连接同一2.4 GHz热点

## 1. 开发方式

MaixCam采用“VS Code本地编辑 + SSH/SCP远程运行”模式：

```text
本地Git源码（唯一可信源）
        │ VS Code任务调用scp
        ▼
/root/robot-platform/（设备部署目录）
        │ VS Code任务调用ssh
        ▼
    Python运行与终端日志
```

不使用VS Code Remote-SSH打开远端工作区。MaixCam Pro是RISC-V 64位设备且内存约128 MB；微软Remote-SSH没有提供riscv64支持，远端资源也低于其建议值。尝试连接会要求安装无法运行的VS Code Server。

MaixVision 1.2.2继续用于实时图像预览、色彩阈值、设备发现、文件浏览和系统恢复，但源码编辑、Git版本和常规部署统一在VS Code。

参考：

- [MaixCAM快速开始](https://wiki.sipeed.com/maixpy/doc/zh/README_MaixCAM.html)
- [MaixVision开发与文件传输](https://wiki.sipeed.com/maixpy/doc/en/basic/maixvision.html)
- [VS Code Remote-SSH系统要求](https://code.visualstudio.com/docs/remote/ssh)

## 2. SSH入口

本机SSH配置使用别名：

```text
robot-maixcam
```

它通过mDNS设备名连接，不依赖可能变化的DHCP地址，并使用项目专用Ed25519密钥。私钥和真实网络凭据只保存在本机，不进入仓库。

命令行验证：

```powershell
ssh robot-maixcam
```

若mDNS暂时失效，先在设备“设置→设备信息”确认IP，再排查热点客户端互访；不要把临时IP硬编码到业务代码。

## 3. VS Code任务

从“终端→运行任务”选择：

- `MaixCam: Check SSH`：只读输出设备身份、系统和版本文件。
- `MaixCam: Upload probe`：建立独立部署目录并上传无运动探针。
- `MaixCam: Run probe`：上传后在设备执行探针并回读JSON状态。
- `MaixCam: SSH terminal`：打开交互式设备终端。

探针不导入 `maix`，不会初始化摄像头、UART、GPIO或运动链路。MaixPy 4.12.5中，即使仅执行 `import maix` 也会初始化默认通信协议并占用UART0，因此“只读诊断”应避免导入该包。

## 4. 设备目录边界

- `/root/robot-platform/`：本项目独立开发与部署目录。
- `/maixapp/`：系统应用和已安装应用；本阶段只读。
- `/boot/`：系统启动与网络配置；本阶段只读。
- `src/maixcam/`：本地可信源码。
- `device-backups/maixcam/`：本地忽略的设备备份。

当前设备自启动应用为 `num`。本目标不改变自启动、不覆盖 `/maixapp/apps/`，也不运行原始串口或机械臂案例。

## 5. 已有备份与恢复

配置前备份位于本机Git忽略目录：

```text
device-backups/maixcam/2026-08-31-maixcam-6c7d-preconfig/
```

备份包含 `/root`、`/maixapp` 和 `/boot`，共872个文件，并生成本地SHA-256清单。备份中包含Wi-Fi配置和设备数据，不得提交或对外发送。

恢复优先级：

1. SSH可用时，从备份选择性恢复单个应用或配置。
2. Wi-Fi不可用时，通过设备屏幕重新配置。
3. 无线不可用时，使用USB虚拟网卡连接MaixVision或SSH。
4. 只有系统损坏且前述路径均失败时，才使用只读资料库中的固件镜像重刷TF卡。

## 6. 尚未接入

- 摄像头采集与实时预览程序。
- MaixCam到ESP32的UART链路。
- MaixCam到TCP232/机械臂LAN1的UART链路。
- 统一控制台状态和视频接口。

这些功能应分别建立目标并先完成模拟或无运动验证；任何可能触发底盘或机械臂运动的测试必须升级到L3/L4安全门。
