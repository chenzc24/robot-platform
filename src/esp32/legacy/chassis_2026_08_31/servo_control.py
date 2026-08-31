"""
预留舵机学生控制接口。

常用接口：
- init_reserve_servos() / init_reserve_servo(servo_id, ...)
- set_reserve_servo_angle(servo_id, angle)
- read_reserve_servo_angle(servo_id)

所有入口角度都会先按 robot_config.py 中的限位裁剪，再下发到底层总线。

作者 王笑
日期 20260701
"""

from robot_config import (
    RESERVE_SERVO_ENABLED,
    RESERVE_SERVO_IDS,
    RESERVE_SERVO_SIGNS,
    RESERVE_SERVO_INIT_ANGLE_DEG,
    RESERVE_SERVO_MAX_DEG,
    RESERVE_SERVO_MIN_DEG,
    clamp,
)

_RESERVE_SERVO_ID_MIN = 0
_RESERVE_SERVO_ID_MAX = 254
_RESERVE_SERVO_SPEED_DEG_S = 60.0


def get_all_servo_ids():
    """返回上电初始化需要处理的全部预留舵机 ID。"""
    if RESERVE_SERVO_ENABLED:
        return tuple(_validate_reserve_servo_id(sid) for sid in RESERVE_SERVO_IDS)
    return ()


def validate_reserve_servo_config():
    """检查预留舵机配置表，启用时缺少任一 ID 配置会抛出 ValueError。"""
    if not RESERVE_SERVO_ENABLED:
        return True
    for servo_id in get_all_servo_ids():
        _reserve_sign(servo_id)
        _reserve_init_angle(servo_id)
        _reserve_limits(servo_id)
    return True


def _validate_reserve_servo_id(servo_id):
    servo_id = int(servo_id)
    if servo_id < _RESERVE_SERVO_ID_MIN or servo_id > _RESERVE_SERVO_ID_MAX:
        raise ValueError("reserve servo_id must be in 0~254: %s" % servo_id)
    return servo_id


def _safe_sign(sign):
    return 1 if sign == 0 else sign


def _reserve_sign(servo_id):
    sign = _reserve_value(servo_id, RESERVE_SERVO_SIGNS, "RESERVE_SERVO_SIGNS")
    if sign not in (1, -1):
        raise ValueError("reserve servo sign must be 1 or -1: %s" % sign)
    return sign


def _reserve_init_angle(servo_id):
    return _reserve_value(
        servo_id,
        RESERVE_SERVO_INIT_ANGLE_DEG,
        "RESERVE_SERVO_INIT_ANGLE_DEG",
    )


def _reserve_limits(servo_id):
    min_deg = _reserve_value(
        servo_id,
        RESERVE_SERVO_MIN_DEG,
        "RESERVE_SERVO_MIN_DEG",
    )
    max_deg = _reserve_value(
        servo_id,
        RESERVE_SERVO_MAX_DEG,
        "RESERVE_SERVO_MAX_DEG",
    )
    if float(min_deg) > float(max_deg):
        raise ValueError("reserve servo min angle greater than max angle: %s" % servo_id)
    return min_deg, max_deg


def _reserve_value(servo_id, table, name):
    servo_id = _validate_reserve_servo_id(servo_id)
    try:
        return table[servo_id]
    except KeyError:
        raise ValueError("servo_id %s missing in %s" % (servo_id, name))


class ServoControl:
    def __init__(self, servo_bus):
        validate_reserve_servo_config()
        self.servo_bus = servo_bus

    def init_reserve_servos(self):
        """
        初始化全部预留舵机：仅在 RESERVE_SERVO_ENABLED=True 时生效。
        将 RESERVE_SERVO_IDS 中的每个舵机转到各自配置的初始角。
        """
        if not RESERVE_SERVO_ENABLED:
            return False
        for servo_id in get_all_servo_ids():
            self.init_reserve_servo(servo_id)
        return True

    def init_reserve_servo(self, servo_id, angle_deg=None):
        """
        初始化指定 ID 的预留舵机。
        angle_deg 省略时使用该 ID 在 RESERVE_SERVO_INIT_ANGLE_DEG 中的配置。
        """
        if not RESERVE_SERVO_ENABLED:
            return False
        servo_id = _validate_reserve_servo_id(servo_id)
        if angle_deg is None:
            angle_deg = _reserve_init_angle(servo_id)
        return self.set_reserve_servo_angle(servo_id, angle_deg)

    def set_reserve_servo_angle(self, servo_id, angle_deg):
        """控制指定 ID 的预留舵机角度，使用速度型位置控制。"""
        if not RESERVE_SERVO_ENABLED:
            return False
        servo_id = _validate_reserve_servo_id(servo_id)
        angle_deg = self._limit_reserve(servo_id, angle_deg)
        sign = _reserve_sign(servo_id)
        self.servo_bus.set_angles(
            ((servo_id, angle_deg * sign),),
            speed_deg_s=_RESERVE_SERVO_SPEED_DEG_S,
        )
        return True

    def read_reserve_servo_angle(self, servo_id):
        """轮询读取指定 ID 的预留舵机角度；未启用时返回 None。"""
        if not RESERVE_SERVO_ENABLED:
            return None
        servo_id = _validate_reserve_servo_id(servo_id)
        angle = self.servo_bus.read_angle(servo_id)
        if angle is None:
            return None
        return self._remove_sign(angle, _reserve_sign(servo_id))

    @staticmethod
    def _limit_reserve(servo_id, angle):
        min_deg, max_deg = _reserve_limits(servo_id)
        return clamp(float(angle), min_deg, max_deg)

    @staticmethod
    def _remove_sign(value, sign):
        if value is None:
            return None
        return float(value) / _safe_sign(sign)
