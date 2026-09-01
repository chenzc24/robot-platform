import pathlib
import sys
import unittest
import json

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))

from control_envelope import EnvelopeError, EnvelopeStreamDecoder, encode_message, lifecycle
from motion_link import MotionLinkError, decode_fields, decode_frame, encode_fields, encode_frame


def command():
    return {"version": 1, "kind": "command", "message_id": "m1", "sequence": 1,
            "target": "arm", "name": "arm.ping", "ttl_ms": 1000, "payload": {}}


class EnvelopeTests(unittest.TestCase):
    def test_round_trip_and_lifecycle_are_strict(self):
        decoder = EnvelopeStreamDecoder()
        messages, errors = decoder.feed(encode_message(command()))
        self.assertEqual(errors, [])
        self.assertEqual(messages[0]["message_id"], "m1")
        response = lifecycle(command(), "DONE", {"answer": "pong"})
        self.assertEqual(EnvelopeStreamDecoder().feed(encode_message(response))[0][0]["lifecycle"], "DONE")

    def test_rejects_crlf_and_extra_fields(self):
        bad = command(); bad["extra"] = 1
        with self.assertRaises(EnvelopeError): encode_message(bad)
        self.assertEqual(EnvelopeStreamDecoder().feed(b'{"x":1}\r\n')[1], ["invalid_terminator"])

    def test_control_envelope_golden_vector(self):
        vector = json.loads((ROOT / "protocol" / "control-envelope-v1-vectors.json").read_text())["vectors"][0]
        self.assertEqual(encode_message(vector["message"]), vector["frame"].encode("ascii"))


class MotionLinkTests(unittest.TestCase):
    def test_rpa2_frame_and_ordered_fields_round_trip(self):
        payload = encode_fields((("joint_deg", "0,0,0,0,0,0"), ("accel_pct", 5), ("speed_pct", 5), ("blend_pct", 0)))
        frame = encode_frame("RPA2", "MOVEJ", 3, 1000, payload)
        parsed = decode_frame(frame)
        self.assertEqual(parsed["sequence"], 3)
        self.assertEqual(decode_fields(parsed["payload"], ("joint_deg", "accel_pct", "speed_pct", "blend_pct"))["blend_pct"], "0")

    def test_bad_crc_and_reordered_fields_fail_closed(self):
        frame = bytearray(encode_frame("RPA2", "PING", 1, 1000))
        frame[-2] = ord("0") if frame[-2] != ord("0") else ord("1")
        with self.assertRaises(MotionLinkError): decode_frame(frame)
        with self.assertRaises(MotionLinkError): decode_fields("b=2;a=1", ("a", "b"))

    def test_motion_link_golden_vector(self):
        vector = json.loads((ROOT / "protocol" / "motion-link-v1-vectors.json").read_text())["vectors"][0]
        self.assertEqual(encode_frame(vector["marker"], vector["type"], vector["sequence"], vector["ttl_ms"], vector["payload"]), vector["frame"].encode("ascii"))
