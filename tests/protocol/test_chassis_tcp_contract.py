"""Contract tests for RCP1/TCP non-motion chassis messages."""

import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))

from chassis_tcp import (
    MAX_FRAME_BYTES,
    ChassisTcpFrameError,
    MessageStreamDecoder,
    decode_message,
    encode_message,
)


class ChassisTcpContractTests(unittest.TestCase):
    def test_golden_vectors_round_trip(self):
        vectors = json.loads(
            (ROOT / "protocol/chassis-tcp-v1-vectors.json").read_text("utf-8")
        )["vectors"]
        for vector in vectors:
            encoded = encode_message(
                vector["type"],
                vector["sequence"],
                vector["ttl_ms"],
                vector["payload"],
            )
            self.assertEqual(encoded.decode("ascii"), vector["frame"])
            self.assertEqual(decode_message(encoded)["type"], vector["type"])

    def test_fragmented_and_combined_frames_recover(self):
        first = encode_message("PING", 2, 1000, {})
        second = encode_message("STATUS", 3, 1000, {})
        decoder = MessageStreamDecoder()
        messages, errors = decoder.feed(first[:7])
        self.assertEqual((messages, errors), ([], []))
        messages, errors = decoder.feed(first[7:] + second)
        self.assertEqual([item["type"] for item in messages], ["PING", "STATUS"])
        self.assertEqual(errors, [])

    def test_oversized_frame_is_discarded_then_recovers(self):
        decoder = MessageStreamDecoder()
        valid = encode_message("PING", 1, 1000, {})
        messages, errors = decoder.feed(b"x" * (MAX_FRAME_BYTES + 1) + b"\n" + valid)
        self.assertEqual(errors, ["frame_too_long"])
        self.assertEqual(messages[0]["type"], "PING")

    def test_invalid_json_fields_ascii_and_terminator_are_rejected(self):
        cases = (
            b"not-json\n",
            b'{"version":1}\n',
            encode_message("PING", 1, 1000, {})[:-1],
            b"\xff\n",
        )
        for frame in cases:
            with self.assertRaises(ChassisTcpFrameError):
                decode_message(frame)

    def test_types_sequence_ttl_and_payload_are_bounded(self):
        invalid = (
            ("VELOCITY", 1, 1000, {}),
            ("PING", 0, 1000, {}),
            ("PING", 1, 99, {}),
            ("PING", 1, 1000, {"extra": True}),
            ("HELLO", 1, 1000, {"client": "Bad Client"}),
            ("ERROR", 1, 0, {"code": "Bad Code"}),
        )
        for values in invalid:
            with self.assertRaises(ChassisTcpFrameError):
                encode_message(*values)

    def test_response_payloads_and_ttl_are_exact(self):
        with self.assertRaises(ChassisTcpFrameError):
            encode_message("STATE", 1, 1, {"service": "safe_idle", "motion_enabled": False})
        with self.assertRaises(ChassisTcpFrameError):
            encode_message("STATE", 1, 0, {"service": "moving", "motion_enabled": True})


if __name__ == "__main__":
    unittest.main()
