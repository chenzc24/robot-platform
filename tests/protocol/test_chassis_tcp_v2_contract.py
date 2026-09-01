"""Contract tests for motion-capable RCP/TCP v2 chassis messages."""

import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))

import chassis_tcp
from chassis_tcp_v2 import (
    MAX_FRAME_BYTES,
    ChassisTcpV2FrameError,
    MessageStreamDecoder,
    decode_message,
    encode_message,
)


class ChassisTcpV2ContractTests(unittest.TestCase):
    def test_golden_vectors_round_trip(self):
        vectors = json.loads(
            (ROOT / "protocol/chassis-tcp-v2-vectors.json").read_text("utf-8")
        )["vectors"]
        for vector in vectors:
            encoded = encode_message(
                vector["type"],
                vector["sequence"],
                vector["ttl_ms"],
                vector["payload"],
            )
            self.assertEqual(encoded.decode("ascii"), vector["frame"])
            self.assertEqual(decode_message(encoded)["payload"], vector["payload"])

    def test_v1_contract_remains_non_motion_and_versioned_separately(self):
        self.assertEqual(chassis_tcp.PROTOCOL_VERSION, 1)
        with self.assertRaises(chassis_tcp.ChassisTcpFrameError):
            chassis_tcp.encode_message(
                "VELOCITY",
                1,
                500,
                {"vx_mm_s": 0, "vy_mm_s": 0, "omega_mrad_s": 0, "hold_ms": 250},
            )
        with self.assertRaises(ChassisTcpV2FrameError):
            decode_message(chassis_tcp.encode_message("PING", 1, 1000, {}))

    def test_fragmented_combined_and_oversized_streams(self):
        first = encode_message("PING", 2, 1000, {})
        second = encode_message("STATUS", 3, 1000, {})
        decoder = MessageStreamDecoder()
        messages, errors = decoder.feed(first[:9])
        self.assertEqual((messages, errors), ([], []))
        messages, errors = decoder.feed(first[9:] + second)
        self.assertEqual([item["type"] for item in messages], ["PING", "STATUS"])
        self.assertEqual(errors, [])
        messages, errors = decoder.feed(
            b"x" * (MAX_FRAME_BYTES + 1) + b"\n" + first
        )
        self.assertEqual(errors, ["frame_too_long"])
        self.assertEqual(messages[0]["type"], "PING")

    def test_request_ranges_and_exact_payloads_are_enforced(self):
        invalid = (
            ("HELLO", 1, 1000, {"client": "console", "credential": "short"}),
            ("ACQUIRE", 1, 1000, {"lease_ms": 249}),
            ("VELOCITY", 1, 500, {"vx_mm_s": 601, "vy_mm_s": 0, "omega_mrad_s": 0, "hold_ms": 250}),
            ("VELOCITY", 1, 500, {"vx_mm_s": 0, "vy_mm_s": 0, "omega_mrad_s": 0, "hold_ms": 99}),
            ("STOP", 1, 1000, {"extra": True}),
            ("PING", 0, 1000, {}),
            ("PING", 1, 99, {}),
        )
        for values in invalid:
            with self.assertRaises(ChassisTcpV2FrameError):
                encode_message(*values)

    def test_state_and_lifecycle_responses_are_exact(self):
        state = {
            "service_state": "ready",
            "chassis_state": "disabled",
            "motion_permitted": False,
            "authenticated": True,
            "lease_active": False,
            "lease_owner": "none",
            "lease_remaining_ms": 0,
            "hold_remaining_ms": 0,
            "last_error": "none",
        }
        self.assertEqual(
            decode_message(encode_message("STATE", 4, 0, state))["payload"], state
        )
        done = {"command": "STOP", "state": "enabled_stopped"}
        self.assertEqual(
            decode_message(encode_message("DONE", 5, 0, done))["payload"], done
        )
        with self.assertRaises(ChassisTcpV2FrameError):
            encode_message("DONE", 5, 0, {"command": "PING", "state": "ready"})

    def test_invalid_json_ascii_and_terminator_are_rejected(self):
        for frame in (b"not-json\n", b'{"version":2}\n', b"\xff\n", b"{}\r\n"):
            with self.assertRaises(ChassisTcpV2FrameError):
                decode_message(frame)


if __name__ == "__main__":
    unittest.main()
