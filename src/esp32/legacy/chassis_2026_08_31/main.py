"""
麦克纳姆轮小车示例主程序。

底层协议已经拆成库：
- motor_lib.py：电机 CAN 速度模式
- servo_lib.py：Fashion Star 舵机二进制协议
- servo_control.py：预留舵机学生控制接口
- chassis_control.py：麦克纳姆轮底盘组合控制
- ps2_lib.py：PS2 手柄底层读取和安全接收
- ps2_control.py：PS2 遥控业务逻辑
- robot_config.py：引脚、速度上限、车体尺寸等配置

作者 王笑
日期 20260701
"""

import time, _thread, sys, machine
time.sleep(3)


from machine import UART
from esp32 import CAN

from chassis_control import MecanumChassis
from motor_lib import MotorBus
from ps2_control import ps2_loop
from ps2_lib import PS2Controller, PS2Receiver
from servo_control import ServoControl, get_all_servo_ids
from servo_lib import ServoBus
from robot_config import (
    CAN_BAUDRATE,
    CAN_BUS_ID,
    CAN_RX,
    CAN_TX,
    PS2_CLK,
    PS2_CS,
    PS2_DI,
    PS2_DO,
    RESERVE_SERVO_ENABLED,
    RESERVE_SERVO_IDS,
    RUN_MODE,
    SERVO_UART_BAUD,
    SERVO_UART_ID,
    SERVO_UART_RX,
    SERVO_UART_TX,
    CAMERA_UART_ID,
    CAMERA_UART_BAUD,
    CAMERA_UART_TX,
    CAMERA_UART_RX,
)

#定义变量
camera_data = {"value": None}

# CAN 初始化

camera_uart = UART(
    CAMERA_UART_ID,
    CAMERA_UART_BAUD,
    tx=CAMERA_UART_TX,
    rx=CAMERA_UART_RX,
    timeout=64
)

try:
    can = CAN(
        CAN_BUS_ID,
        mode=CAN.NORMAL,
        baudrate=CAN_BAUDRATE,
        tx=CAN_TX,
        rx=CAN_RX,
    )
except Exception:
    print("CAN硬件占用。触发系统级软复位，请点击STOP重新连接。")
    time.sleep(1)
    machine.reset()
can.clear_rx_queue()

# 电机初始化
motor_bus = MotorBus(can)
chassis = MecanumChassis(motor_bus)

# 舵机初始化
servo_control = None
if RESERVE_SERVO_ENABLED:
    servo_uart = UART(
        SERVO_UART_ID,
        SERVO_UART_BAUD,
        tx=SERVO_UART_TX,
        rx=SERVO_UART_RX,
        timeout=64,
    )
    servo_bus = ServoBus(servo_uart)
    servo_control = ServoControl(servo_bus)
    reserve_servo_ids = get_all_servo_ids()
    if reserve_servo_ids:
        servo_bus.reset_turns_polling(reserve_servo_ids)
        servo_bus.lock_all(reserve_servo_ids)
    servo_control.init_reserve_servos()


def re_uart(uart):
    global camera_data, camera_uart
    try:
        while True:
            if uart.any() and uart == camera_uart :
                data                 = uart.read()
                camera_data["value"] = data.decode("utf-8", "replace")
                print("串口1收到数据:", camera_data["value"])
            time.sleep_ms(10)       # 防止形成阻塞              
    except UnicodeError:
        print("【成功拦截乱码】串口1收到一串无法识别的非文本数据:")
        pass
        _thread.start_new_thread(re_uart, (uart, ))


#打开多线程
_thread.start_new_thread(re_uart, (camera_uart, ))

def main():
    global camera_data
    try:
        #手柄初始化及控制入口
        if RUN_MODE == "ps2":
            chassis.prepare()
            ps2_controller = PS2Controller(di=PS2_DI, do=PS2_DO, cs=PS2_CS, clk=PS2_CLK)
            ps2_controller.init_vibration()
            ps2 = PS2Receiver(ps2_controller, 30, True)
            ps2.start()
            try:
                ps2_loop(chassis,servo_control, ps2, camera_data, camera_uart)
            finally:
                ps2.stop()
                chassis.disable()
            return
        #示例函数
        chassis.prepare()
        print("RUN_MODE=idle，电机已默认使能。学生可在示例区编写一次性控制程序。")

        # ================= 学生控制示例 =================
        # 使用方法：每次只取消一小段示例代码的注释，确认安全后再运行。
        # 注意：调试底盘前建议先架空车轮，避免小车突然运动。

        # 示例 1：麦克纳姆轮基础动作组合测试。
        # 每个动作运行 2 秒，然后停车停顿 1 秒。
        print("示例 1：麦克纳姆轮基础动作组合测试，每个动作运行 2 秒，停顿 1 秒。")

        print("前进 vx=0.20 m/s")
        chassis.drive(vx=0.20, vy=0.0, omega=0.0)
        time.sleep(2) # 必须要延迟，让指令有执行时间，否则指令会被立即覆盖。
        chassis.stop()
        time.sleep(1)

        print("后退 vx=-0.20 m/s")
        chassis.drive(vx=-0.20, vy=0.0, omega=0.0)
        time.sleep(2)
        chassis.stop()
        time.sleep(1)

        print("向左平移 vy=0.20 m/s")
        chassis.drive(vx=0.0, vy=0.20, omega=0.0)
        time.sleep(2)
        chassis.stop()
        time.sleep(1)

        print("向右平移 vy=-0.20 m/s")
        chassis.drive(vx=0.0, vy=-0.20, omega=0.0)
        time.sleep(2)
        chassis.stop()
        time.sleep(1)

        print("原地左转 omega=0.30 rad/s")
        chassis.drive(vx=0.0, vy=0.0, omega=0.30)
        time.sleep(2)
        chassis.stop()
        time.sleep(1)

        print("前进+左平移+左转")
        chassis.drive(vx=0.15, vy=0.10, omega=0.20)
        time.sleep(2)
        chassis.stop()
        time.sleep(1)

        # 示例 2：原地转向辅助接口测试。
        # pivot_turn 正数向左转，负数向右转。
        print("示例 2：原地转向辅助接口测试，左转 2 秒，右转 2 秒。")

        print("pivot_turn 原地左转 omega=0.30 rad/s")
        chassis.pivot_turn(0.30)
        time.sleep(2)
        chassis.stop()
        time.sleep(1)

        print("pivot_turn 原地右转 omega=-0.30 rad/s")
        chassis.pivot_turn(-0.30)
        time.sleep(2)
        chassis.stop()
        time.sleep(1)

        # 示例 3：直接控制四个轮子的目标角速度，运行 1 秒后停车。
        # 参数顺序：左前、右前、左后、右后，单位 rad/s。
        # 注意：这是轮子角速度接口，会自动处理电机安装方向。
        print("示例 3：直接控制四个轮子的目标角速度，运行 1 秒后停车。")
        chassis.drive_wheel_speeds(
            left_front=2.0,
            right_front=2.0,
            left_rear=2.0,
            right_rear=2.0,
        )
        time.sleep(1)
        chassis.stop()
        time.sleep(1)

        # 示例 4：预留舵机测试。
        # 需先在 robot_config.py 设置 RESERVE_SERVO_ENABLED = True，并在 RESERVE_SERVO_IDS 中填写 ID。
        print("示例 4：预留舵机测试。")
        if not RESERVE_SERVO_ENABLED:
            print("预留舵机未启用，请先在 robot_config.py 设置 RESERVE_SERVO_ENABLED = True。")
        elif not RESERVE_SERVO_IDS:
            print("未填写预留舵机 ID，请先在 robot_config.py 的 RESERVE_SERVO_IDS 中填写 ID。")
        else:
            reserve_id = RESERVE_SERVO_IDS[0]
            servo_control.set_reserve_servo_angle(reserve_id, 30.0)
            time.sleep(1)
            angle = servo_control.read_reserve_servo_angle(reserve_id)
            print("预留舵机 ID=%d 当前角度：" % reserve_id, angle)
            servo_control.set_reserve_servo_angle(reserve_id, -2.0)
            time.sleep(1)

        chassis.disable()
        print("测试结束，电机已失能。")

    except Exception as err:
        print("错误代码：", err)
        try:
            chassis.disable()
        except Exception:
            pass


if __name__ == "__main__":
    main()
