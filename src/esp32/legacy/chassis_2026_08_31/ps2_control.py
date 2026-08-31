"""
PS2 遥控业务控制逻辑。

本文件负责把 PS2 按键和摇杆映射到麦克纳姆轮底盘动作。

映射：
- 左摇杆 X：原地转向 / omega
- 右摇杆 Y：vx 前进后退
- 右摇杆 X：vy 左右平移
- R1：停车
- X：电机停车并失能
- Triangle：重新初始化并使能电机
- SELECT：退出 PS2 控制循环

作者 王笑
日期 20260701
"""

import time

from chassis_control import (
    MAX_CHASSIS_LINEAR_SPEED_M_S,
    MAX_CHASSIS_OMEGA_RAD_S,
)
from robot_config import (
    clamp,
    RESERVE_SERVO_ENABLED,
    RESERVE_SERVO_IDS,  
)

_PS2_DEADZONE = 12
_PS2_CONTROL_INTERVAL_MS = 50


##########################################循迹部分郑养波
from machine import Pin
from hcsr04 import Robot_HCSR04
systick_ms_gs = 0						#定距跟随（gensui）的上一次时间戳ms
systick_ms_xjbz = 0						#循迹避障（ziyou bizhang）的上一次时间戳ms
xunji_fl_pin = 0						#直行方向的左循迹传感器引脚
xunji_fr_pin = 0						#直行方向的右循迹传感器引脚
xunji_rf_pin = 0						#侧面方向的前循迹传感器引脚
xunji_rb_pin = 0						#侧面方向的后循迹传感器引脚
def setup_sensor():
    global sensor
    setup_xunji(15,7,47,21)      
    sensor = Robot_HCSR04(trigger_pin=14, echo_pin=13)   # 定义超声波模块Tring控制管脚及超声波模块Echo控制管脚,S3接口

# 循迹避障
def xunji_bizhang(chassis,ps2):
    global systick_ms_xjbz, sensor
    if millis() - systick_ms_xjbz > 50:
        systick_ms_xjbz = millis()
        dis = sensor.distance_cm()
        print (dis, 'cm')  # 打印超声波距离值
        #如果超声波检测到障碍物（距离小于20厘米），小车停止
        while 1:
            ##测距
            dis = sensor.distance_cm()
            #避障检测-zyb
            if dis > 0 and dis < 20:
                print (dis, 'cm')  # 打印超声波距离值
                print("距离太近，请停车！")
                #添加小车停止指令-zyb
                chassis.stop()
                time.sleep(0.01)
            ##检测ps2
            ps2.update()
            fresh, buttons, lx, _ly, rx, ry, _age_ms = ps2.snapshot()
            if button_pressed(buttons, ps2.PS2_BTN_L2):
                break
                print("退出循迹")
           
            ##读取四个循迹探头状态（0=黑线，1=白底）
            fl = xunji_fl()
            fr = xunji_fr()
            rf = xunji_rf()
            rb = xunji_rb()
            print("fl=%d fr=%d rf=%d rb=%d" % (fl, fr, rf, rb))
            #第1种情况  X方向 全压在黑线上；Y方向也压在黑线上，说明在十字路口
            if fl == 1 and xunji_fr() == 1 and xunji_rf() == 1 and xunji_rb()== 1:
                print("车子在十字路口，正在作业")
                chassis.stop()
                sleep_ms(100)
            
            #第2种情况  X方向 全压在黑线上；Y方向没有压在黑线上，说明车子正在直行            
            if xunji_fl() == 1 and xunji_fr() == 1 and xunji_rf() == 0 and xunji_rb() == 0:
                print("车子正在直行")
                chassis.drive(0.1, 0, 0)
                time.sleep(0.5) 

            #第3种情况  X方向 只有右侧在黑线上；Y方向没有压在黑线上，说明车子左偏了，要右转 
            if xunji_fl() == 0 and xunji_fr() == 1 and xunji_rf() == 0 and xunji_rb() == 0:
                print("车子左偏，正在右转")
                chassis.drive(0.05, 0, -0.2)
                time.sleep(0.5) 

            #第4种情况  X方向 只有左侧在黑线上；Y方向没有压在黑线上，说明车子右偏了，要左转 
            if xunji_fl() == 1 and xunji_fr() == 0 and xunji_rf() == 0 and xunji_rb() == 0:
                print("车子右偏，正在左转")
                chassis.drive(0.05, 0, 0.2)
                time.sleep(0.5)
            else:
                chassis.stop()
                sleep_ms(100)

def setup_xunji(xunji_fl_PIN,xunji_fr_PIN,xunji_rf_PIN,xunji_rb_PIN,):
    global xunji_fl_pin,xunji_fr_pin,xunji_rf_pin,xunji_rb_pin
    #设置循迹传感器的两个引脚为输入模式

    xunji_fl_pin = Pin(xunji_fl_PIN, Pin.IN, Pin.PULL_UP)    # 将对应引脚设置为输入模式		PIN34
    xunji_fr_pin = Pin(xunji_fr_PIN, Pin.IN, Pin.PULL_UP)    # 将对应引脚设置为输入模式		PIN36
    xunji_rf_pin = Pin(xunji_rf_PIN, Pin.IN)    # 将对应引脚设置为输入模式		PIN35
    xunji_rb_pin = Pin(xunji_rb_PIN, Pin.IN)    # 将对应引脚设置为输入模式		PIN39
        
def xunji_fl():
    return xunji_fl_pin.value()
def xunji_fr():
    return xunji_fr_pin.value()
def xunji_rf():
    return xunji_rf_pin.value()
def xunji_rb():
    return xunji_rb_pin.value()

#获取系统时间，毫秒为单位
def millis():
    return int(time.time_ns()//1000000)
systick_ms_xjbz = millis()
setup_sensor()
##########################################循迹部分郑养波


def sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(ms)
    else:
        time.sleep(ms / 1000.0)


def map_joystick(raw_val, center=128, deadzone=_PS2_DEADZONE):
    offset = int(raw_val) - center
    if abs(offset) <= deadzone:
        return 0
    sign = 1 if offset > 0 else -1
    active_range = 127.0 - deadzone
    mapped = int(((abs(offset) - deadzone) / active_range) * 100.0) * sign
    return clamp(mapped, -100, 100)


def button_pressed(data, btn):
    return (data & btn) == btn

# ==========================
# 主循环控制：演示如何从底层获取 PS2 控制数据，并映射到底盘动作。
# ==========================
def ps2_loop(chassis, servo_control, ps2, data, serial):
    print("PS2 控制：左摇杆左右原地转向，右摇杆前后控制 vx，右摇杆左右控制 vy，R1停车，X失能，三角使能，SELECT退出。")
    while True:
        ps2.update()
        serial_data = data["value"]
        if serial_data is not None:
            serial.write("ok")
            if len(serial_data) != 0:
                print(f"接受信息 {serial_data}")
            else:
                print(f"警告：数据长度异常，期望6位，实际{len(serial_data)}位。原始数据: {serial_data}")
            data["value"] = None
        fresh, buttons, lx, _ly, rx, ry, _age_ms = ps2.snapshot()
        if not fresh:
            chassis.stop()
            sleep_ms(_PS2_CONTROL_INTERVAL_MS)
            continue

        if button_pressed(buttons, ps2.PS2_BTN_SELECT):
            chassis.stop()
            print("SELECT：退出 PS2 控制。")
            break

        if button_pressed(buttons, ps2.PS2_BTN_R1):
            chassis.stop()
            sleep_ms(100)
            continue

        if button_pressed(buttons, ps2.PS2_BTN_CROSS):
            chassis.disable()
            sleep_ms(200)
            continue

        if button_pressed(buttons, ps2.PS2_BTN_TRIANGLE):
            chassis.enable_motors()
            sleep_ms(200)
            continue
        # 练习1 按下遥控器 up 键 启动指定功能
        if button_pressed(buttons, ps2.PS2_BTN_UP):
            # 在此添加你的程序


            # end 
            continue
        
##########################################循迹部分郑养波        
        if button_pressed(buttons, ps2.PS2_BTN_L1):
            # 按L1开启循迹功能

            xunji_bizhang(chassis,ps2)
            # end 
            continue
##########################################循迹部分郑养波
        
        turn = map_joystick(lx)
        forward = -map_joystick(ry)
        strafe_left = -map_joystick(rx)

        vx = forward / 100.0 * MAX_CHASSIS_LINEAR_SPEED_M_S
        vy = strafe_left / 100.0 * MAX_CHASSIS_LINEAR_SPEED_M_S
        omega = -turn / 100.0 * MAX_CHASSIS_OMEGA_RAD_S

        chassis.drive(vx, vy, omega)
        sleep_ms(_PS2_CONTROL_INTERVAL_MS)

