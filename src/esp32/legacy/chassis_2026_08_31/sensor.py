'''
作者：郑养波
日期：2026年8月1日
定义了定距跟随、自由避障、智能循迹、循迹避障等功能 可以单独进行测试
建议其他传感器在此定义
'''
from machine import Pin
import time
from hcsr04 import Robot_HCSR04

'''
#MOVE_TAG 			0-保留；1—循迹控制；2—自由避障；3—定距跟随
'''
MOVE_TAG = 0

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
def xunji_bizhang():
    global systick_ms_xjbz, sensor
    if millis() - systick_ms_xjbz > 50:
        systick_ms_xjbz = millis()
        dis = sensor.distance_cm()
        print (dis, 'cm')  # 打印超声波距离值
        #如果超声波检测到障碍物（距离小于20厘米），小车停止
        while 1:
            dis = sensor.distance_cm()
            #避障检测-zyb
            if dis > 0 and dis < 20:
                print (dis, 'cm')  # 打印超声波距离值
                print("距离太近，请停车！")
                #添加小车停止指令-zyb
                time.sleep(1)
                
            #检测循迹线 反馈：探头压在白区反馈0；压在黑区反馈1
            print("xunji_fl=",xunji_fl(),"xunji_fr=",xunji_fr(),"xunji_rf=",xunji_rf(),"xunji_rb=",xunji_rb())
            #循迹压在黑线上是0，压在白底上是1
            if xunji_fl() == 1 and xunji_fr() == 1 and xunji_rf() == 1 and xunji_rb() == 1:
                #都压在黑线上，停止开展作业
                time.sleep(0.5)            
            if xunji_fl() == 1 and xunji_fr() == 1:
                #前循迹传感器全在外侧
                time.sleep(0.5) 
            
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

# 程序入口
if __name__ == '__main__':
    
    global uart
    systick_ms_xjbz = millis()
    setup_sensor()
    while 1:
        xunji_bizhang()