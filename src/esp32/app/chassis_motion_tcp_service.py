"""RCP/TCP v2 chassis service with injected authentication and motion hardware."""

import time

from chassis_tcp_v2 import (
    CONTROL_TYPES,
    MessageStreamDecoder,
    encode_message,
)
from control_lease import ControlLeaseError

try:
    _TIMEOUT_ERROR = TimeoutError
except NameError:
    _TIMEOUT_ERROR = ()


def _clock_ms():
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    if hasattr(time, "monotonic"):
        return int(time.monotonic() * 1000)
    return int(time.time() * 1000)


def _ticks_add(value, delta):
    if hasattr(time, "ticks_add"):
        return time.ticks_add(value, delta)
    return value + delta


def _ticks_diff(left, right):
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(left, right)
    return left - right


def _idle_read_error(error):
    if isinstance(error, _TIMEOUT_ERROR):
        return True
    code = getattr(error, "errno", None)
    if code is None and getattr(error, "args", None):
        code = error.args[0]
    return code in (11, 110, 116, 10035)


def fixed_credential_verifier(expected_credential):
    """Build a constant-work local verifier without logging either value."""
    if not isinstance(expected_credential, str) or not expected_credential:
        raise ValueError("expected credential is required")
    expected = expected_credential.encode("ascii")

    def verify(_client_id, supplied_credential):
        try:
            supplied = supplied_credential.encode("ascii")
        except (AttributeError, UnicodeError):
            return False
        difference = len(expected) ^ len(supplied)
        maximum = max(len(expected), len(supplied))
        for index in range(maximum):
            left = expected[index] if index < len(expected) else 0
            right = supplied[index] if index < len(supplied) else 0
            difference |= left ^ right
        return difference == 0

    return verify


class ChassisMotionRequestError(ValueError):
    """A stable request rejection that is safe to expose as an error code."""


class ChassisMotionTcpService:
    """Execute one authenticated v2 request at a time and fail locally safe."""

    def __init__(
        self,
        transport,
        chassis,
        lease,
        authorize=None,
        motion_permitted=False,
        clock_ms=None,
        max_linear_mm_s=None,
        max_omega_mrad_s=None,
        max_hold_ms=None,
    ):
        self.transport = transport
        self.chassis = chassis
        self.lease = lease
        self.authorize = authorize
        self.motion_permitted = motion_permitted is True
        self._clock_ms = clock_ms or _clock_ms
        self.max_linear_mm_s = self._optional_positive_int(
            max_linear_mm_s, "max_linear_mm_s"
        )
        self.max_omega_mrad_s = self._optional_positive_int(
            max_omega_mrad_s, "max_omega_mrad_s"
        )
        self.max_hold_ms = self._optional_positive_int(
            max_hold_ms, "max_hold_ms"
        )
        self.decoder = MessageStreamDecoder()
        self.service_state = "safe_idle"
        self.error_code = None
        self.client_id = None
        self.authenticated = False
        self.close_required = False
        self.last_sequence = 0
        self._last_fingerprint = None
        self._last_responses = None
        self._hold_deadline_ms = None
        self._active_velocity_sequence = None

    @staticmethod
    def _optional_positive_int(value, name):
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("%s must be a positive integer or None" % name)
        return value

    def _response(self, request, response_type, payload):
        return encode_message(response_type, request["sequence"], 0, payload)

    def _error(self, request, code, retryable=False):
        self.error_code = code
        return (
            self._response(
                request,
                "ERROR",
                {"code": code, "retryable": retryable is True},
            ),
        )

    def _phases(self, request, state):
        payload = {"command": request["type"], "state": state}
        return (
            self._response(request, "ACK", payload),
            self._response(request, "DONE", payload),
        )

    def _write_responses(self, responses):
        for response in responses:
            try:
                written = self.transport.write(response)
            except Exception:
                self.force_safe("tcp_write_failed")
                raise
            if written is not None and written != len(response):
                self.force_safe("tcp_short_write")
                raise OSError("tcp_short_write")

    def _lease_owner(self):
        return self.client_id if self.authenticated else None

    def _stop_and_disable(self):
        failed = False
        try:
            self.chassis.stop()
        except Exception:
            failed = True
        try:
            self.chassis.disable()
        except Exception:
            failed = True
        return not failed

    def _require_owner(self):
        owner = self._lease_owner()
        if owner is None or self.lease.owner != owner:
            raise ChassisMotionRequestError("control_not_owned")
        return owner

    def _status_payload(self, now_ms):
        lease_status = self.lease.status()
        hold_remaining_ms = 0
        if self._hold_deadline_ms is not None:
            hold_remaining_ms = max(
                0, _ticks_diff(self._hold_deadline_ms, now_ms)
            )
        return {
            "service_state": self.service_state,
            "chassis_state": getattr(self.chassis, "state", "unknown"),
            "motion_permitted": self.motion_permitted,
            "authenticated": self.authenticated,
            "lease_active": lease_status["active"],
            "lease_owner": lease_status["owner"] or "none",
            "lease_remaining_ms": min(2000, lease_status["remaining_ms"]),
            "hold_remaining_ms": min(500, hold_remaining_ms),
            "last_error": self.error_code or "none",
        }

    def _authenticate(self, request):
        if self.authenticated:
            return self._error(request, "session_started")
        payload = request["payload"]
        allowed = False
        if self.authorize is not None:
            try:
                allowed = self.authorize(payload["client"], payload["credential"])
            except Exception:
                allowed = False
        if allowed is not True:
            self.close_required = True
            return self._error(request, "authentication_failed")
        self.client_id = payload["client"]
        self.authenticated = True
        self.service_state = "ready"
        self.error_code = None
        return (
            self._response(
                request,
                "WELCOME",
                {
                    "service": "chassis",
                    "protocol": 2,
                    "motion_permitted": self.motion_permitted,
                },
            ),
        )

    def _execute(self, request, received_at_ms, now_ms):
        request_type = request["type"]
        if request_type == "HELLO":
            return self._authenticate(request)
        if not self.authenticated:
            return self._error(request, "session_required")
        if _ticks_diff(now_ms, _ticks_add(received_at_ms, request["ttl_ms"])) > 0:
            return self._error(request, "expired")
        if self.service_state == "fault" and request_type not in (
            "PING",
            "STATUS",
            "STOP",
            "DISABLE",
        ):
            return self._error(request, "service_fault")

        try:
            if request_type == "PING":
                self.error_code = None if self.service_state != "fault" else self.error_code
                return (self._response(request, "PONG", {"protocol": 2}),)
            if request_type == "STATUS":
                return (self._response(request, "STATE", self._status_payload(now_ms)),)
            if request_type == "ACQUIRE":
                if self.lease.owner is not None and self.lease.owner != self.client_id:
                    raise ChassisMotionRequestError("control_owned")
                self.lease.acquire(self.client_id, request["payload"]["lease_ms"])
                self.error_code = None
                return self._phases(request, "owned")
            if request_type == "HEARTBEAT":
                self._require_owner()
                self.lease.renew(self.client_id, request["payload"]["lease_ms"])
                self.error_code = None
                return self._phases(request, "owned")
            if request_type == "ENABLE":
                self._require_owner()
                if not self.motion_permitted:
                    raise ChassisMotionRequestError("motion_disabled")
                if getattr(self.chassis, "state", None) != "disabled":
                    raise ChassisMotionRequestError("invalid_chassis_state")
                self.chassis.enable_motors()
                self.error_code = None
                return self._phases(request, "enabled_stopped")
            if request_type == "VELOCITY":
                self._require_owner()
                if not self.motion_permitted:
                    raise ChassisMotionRequestError("motion_disabled")
                if getattr(self.chassis, "state", None) not in (
                    "enabled_stopped",
                    "moving",
                ):
                    raise ChassisMotionRequestError("invalid_chassis_state")
                payload = request["payload"]
                if payload["hold_ms"] > request["ttl_ms"]:
                    raise ChassisMotionRequestError("hold_exceeds_ttl")
                if (
                    self.max_linear_mm_s is not None
                    and payload["vx_mm_s"] * payload["vx_mm_s"]
                    + payload["vy_mm_s"] * payload["vy_mm_s"]
                    > self.max_linear_mm_s * self.max_linear_mm_s
                ):
                    raise ChassisMotionRequestError("linear_speed_limited")
                if (
                    self.max_omega_mrad_s is not None
                    and abs(payload["omega_mrad_s"]) > self.max_omega_mrad_s
                ):
                    raise ChassisMotionRequestError("angular_speed_limited")
                if (
                    self.max_hold_ms is not None
                    and payload["hold_ms"] > self.max_hold_ms
                ):
                    raise ChassisMotionRequestError("hold_duration_limited")
                self.chassis.drive(
                    payload["vx_mm_s"] / 1000.0,
                    payload["vy_mm_s"] / 1000.0,
                    payload["omega_mrad_s"] / 1000.0,
                )
                self._hold_deadline_ms = _ticks_add(now_ms, payload["hold_ms"])
                self._active_velocity_sequence = request["sequence"]
                self.error_code = None
                return self._phases(request, "moving")
            if request_type in ("STOP", "DISABLE"):
                self._hold_deadline_ms = None
                self._active_velocity_sequence = None
                if request_type == "STOP":
                    self.chassis.stop()
                else:
                    self.chassis.disable()
                self.error_code = None if self.service_state != "fault" else self.error_code
                return self._phases(
                    request, getattr(self.chassis, "state", "unknown")
                )
            if request_type == "RELEASE":
                owner = self._require_owner()
                self._hold_deadline_ms = None
                self._active_velocity_sequence = None
                if not self._stop_and_disable():
                    raise RuntimeError("safe_output_failed")
                self.lease.release(owner)
                self.error_code = None
                return self._phases(request, "released")
        except ChassisMotionRequestError as error:
            return self._error(request, str(error))
        except ControlLeaseError:
            return self._error(request, "lease_rejected")
        except Exception:
            self.force_safe("execution_failed")
            return self._error(request, "execution_failed")
        return self._error(request, "unsupported_command")

    @staticmethod
    def _fingerprint(request):
        if request["type"] == "HELLO":
            return None
        return encode_message(
            request["type"],
            request["sequence"],
            request["ttl_ms"],
            request["payload"],
        )

    def handle_message(self, request, received_at_ms=None, now_ms=None):
        now_ms = self._clock_ms() if now_ms is None else now_ms
        received_at_ms = now_ms if received_at_ms is None else received_at_ms
        self.poll_safety(now_ms)
        sequence = request["sequence"]
        fingerprint = self._fingerprint(request)
        if sequence == self.last_sequence:
            if fingerprint is not None and fingerprint == self._last_fingerprint:
                responses = self._last_responses
                self._write_responses(responses)
                return responses
            responses = self._error(request, "sequence_conflict")
            self._write_responses(responses)
            return responses
        if sequence < self.last_sequence:
            responses = self._error(request, "sequence_replay")
            self._write_responses(responses)
            return responses
        responses = self._execute(request, received_at_ms, now_ms)
        self.last_sequence = sequence
        self._last_fingerprint = fingerprint
        self._last_responses = responses if fingerprint is not None else None
        self._write_responses(responses)
        return responses

    def feed(self, data, received_at_ms=None, now_ms=None):
        messages, errors = self.decoder.feed(data)
        if errors:
            self.error_code = errors[-1]
            self.close_required = True
            if self.authenticated:
                self.force_safe("protocol_error")
            return (), errors
        responses = []
        for message in messages:
            if message["type"] not in (
                "HELLO",
                "PING",
                "STATUS",
            ) + CONTROL_TYPES:
                generated = self._error(message, "unsupported_direction")
                self._write_responses(generated)
                responses.extend(generated)
                continue
            responses.extend(
                self.handle_message(message, received_at_ms, now_ms)
            )
        return tuple(responses), errors

    def poll_safety(self, now_ms=None):
        """Stop stale velocity; disable only when the control lease is lost."""
        now_ms = self._clock_ms() if now_ms is None else now_ms
        expired_owner = self.lease.expire_if_needed()
        hold_expired = self._hold_deadline_ms is not None and _ticks_diff(
            now_ms, self._hold_deadline_ms
        ) >= 0
        if expired_owner is None and not hold_expired:
            return None
        reason = "lease_expired" if expired_owner is not None else "velocity_hold_expired"
        sequence = self._active_velocity_sequence
        self._hold_deadline_ms = None
        self._active_velocity_sequence = None
        try:
            if expired_owner is not None:
                if not self._stop_and_disable():
                    raise RuntimeError("safe_output_failed")
            else:
                self.chassis.stop()
            self.error_code = reason
            return {
                "sequence": sequence,
                "event": reason,
                "state": getattr(self.chassis, "state", "unknown"),
            }
        except Exception:
            self._stop_and_disable()
            self.service_state = "fault"
            self.error_code = "watchdog_stop_failed"
            return {
                "sequence": sequence,
                "event": "watchdog_stop_failed",
                "state": "fault",
            }

    def _clear_lease(self):
        owner = self.lease.owner
        if owner is not None:
            try:
                self.lease.release(owner)
            except Exception:
                pass

    def force_safe(self, error_code):
        """Best-effort local stop/disable and require connection replacement."""
        self._hold_deadline_ms = None
        self._active_velocity_sequence = None
        self.error_code = error_code if self._stop_and_disable() else "safe_output_failed"
        self._clear_lease()
        self.service_state = "fault"
        self.close_required = True
        return self.error_code == error_code

    def on_disconnect(self):
        """Clear the session only after attempting local safe output."""
        safe = self._stop_and_disable()
        self._clear_lease()
        self._hold_deadline_ms = None
        self._active_velocity_sequence = None
        self.client_id = None
        self.authenticated = False
        self.last_sequence = 0
        self._last_fingerprint = None
        self._last_responses = None
        self.decoder = MessageStreamDecoder()
        self.close_required = True
        self.service_state = "safe_idle" if safe else "fault"
        self.error_code = "connection_lost" if safe else "safe_output_failed"
        return safe

    def reset_for_connection(self, transport):
        """Attach a fresh connection only after the previous session is safely closed."""
        if self.authenticated or self.lease.owner is not None:
            raise RuntimeError("session_active")
        if self.service_state == "fault":
            raise RuntimeError("service_fault")
        self.transport = transport
        self.close_required = False
        self.last_sequence = 0
        self._last_fingerprint = None
        self._last_responses = None
        self.decoder = MessageStreamDecoder()


class ChassisMotionTcpRuntime:
    """Poll one injected TCP connection and the local watchdog continuously."""

    def __init__(self, service, connection, time_module=None):
        self.service = service
        self.connection = connection
        self.time = time_module or time

    def poll_once(self):
        event = self.service.poll_safety()
        try:
            data = self.connection.recv(512)
        except Exception as error:
            if _idle_read_error(error):
                return event
            self.service.on_disconnect()
            raise
        if data == b"":
            self.service.on_disconnect()
            raise OSError("connection_lost")
        if data:
            self.service.feed(data)
        if self.service.close_required:
            raise OSError("session_close_required")
        return event

    def run_forever(self, poll_interval_ms=5):
        if isinstance(poll_interval_ms, bool) or not isinstance(poll_interval_ms, int):
            raise ValueError("poll_interval_ms must be an integer")
        if not 1 <= poll_interval_ms <= 50:
            raise ValueError("poll_interval_ms must be in 1..50")
        while True:
            self.poll_once()
            if hasattr(self.time, "sleep_ms"):
                self.time.sleep_ms(poll_interval_ms)
            else:
                self.time.sleep(poll_interval_ms / 1000.0)
