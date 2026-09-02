"""Computer-facing, arm-only NDJSON command service for MaixCam."""

from control_envelope import EnvelopeStreamDecoder, encode_message, lifecycle, validate_message
from arm_motion_gateway import ArmMotionGatewayError, arm_payload


MOTION_NAMES = {"arm.move_joint", "arm.move_linear", "arm.gripper", "arm.l3_j1_cycle"}


class ArmCommandService:
    def __init__(self, gateway, admission=None):
        self.gateway, self.admission = gateway, admission
        self.decoder, self.active = EnvelopeStreamDecoder(), None
        self.last_sequence = 0

    @staticmethod
    def _encode(messages):
        return b"".join(encode_message(message) for message in messages)

    def _reply(self, message, state, payload=None):
        return lifecycle(message, state, payload or {})

    def _reject(self, message, code):
        return self._reply(message, "REJECTED", {"error_code": code, "retryable": False})

    def _dispatch(self, message):
        if message["kind"] != "command" or message["target"] != "arm":
            return [self._reject(message, "arm_command_required")]
        if message["sequence"] <= self.last_sequence:
            return [self._reject(message, "sequence_replay")]
        self.last_sequence = message["sequence"]
        if self.active is not None:
            return [self._reject(message, "request_in_flight")]
        try:
            command, payload = arm_payload(message["name"], message["payload"])
            if message["name"] in MOTION_NAMES:
                if self.admission is None or self.admission(message) is not True:
                    return [self._reject(message, "admission_rejected")]
            sequence = self.gateway.start(command, payload, message["ttl_ms"])
        except (ArmMotionGatewayError, ValueError) as error:
            return [self._reject(message, getattr(error, "code", str(error)))]
        self.active = message
        return [self._reply(message, "RECEIVED"), self._reply(message, "ACCEPTED", {"downstream_sequence": sequence})]

    def feed_computer(self, data):
        messages, errors = self.decoder.feed(data)
        replies = []
        for error in errors:
            # A malformed frame has no trusted message id to correlate.
            replies.append({"version": 1, "kind": "event", "message_id": "gateway:invalid", "sequence": 1,
                            "target": "arm", "name": "gateway.protocol", "ttl_ms": 0,
                            "payload": {"error_code": error}})
        for message in messages:
            replies.extend(self._dispatch(message))
        return self._encode(replies)

    def feed_uart(self, data):
        replies = []
        for event, code, frame in self.gateway.feed(data):
            if event == "IGNORED":
                continue
            if self.active is None:
                continue
            if event == "ACK":
                continue
            if event == "RUNNING":
                replies.append(self._reply(self.active, "RUNNING", {"downstream_sequence": frame["sequence"]}))
            elif event == "DONE":
                replies.append(self._reply(self.active, "DONE", {"downstream_sequence": frame["sequence"], "terminal_position": "unknown", "downstream_payload": frame["payload"]}))
                self.active = None
            else:
                replies.append(self._reply(self.active, "FAULT", {"error_code": code or "downstream_fault", "retryable": False}))
                self.active = None
        return self._encode(replies)

    def poll(self):
        outcome = self.gateway.poll()
        if outcome is None or self.active is None:
            return b""
        state = "UNKNOWN" if outcome == "UNKNOWN" else "FAULT"
        message = self._reply(self.active, state, {"error_code": "response_timeout", "retryable": False})
        self.active = None
        return self._encode((message,))

    def snapshot(self):
        return {"gateway": self.gateway.snapshot(), "active_message_id": None if self.active is None else self.active["message_id"],
                "motion_enabled": False, "terminal_position_supported": False, "cancel_supported": False}
