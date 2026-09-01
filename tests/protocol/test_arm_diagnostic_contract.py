"""Contract tests for the no-motion arm diagnostic protocol."""

import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
ARM_DIR = ROOT / "src" / "maixcam" / "arm"
sys.path.insert(0, str(ARM_DIR))

from link_protocol import ArmFrameError, FrameStreamDecoder, decode_frame, encode_frame


class ArmDiagnosticContractTests(unittest.TestCase):
    def test_published_vectors_encode_and_decode(self):
        path = ROOT / "protocol" / "arm-diagnostic-v1-vectors.json"
        contract = json.loads(path.read_text(encoding="utf-8"))
        for vector in contract["vectors"]:
            fields = vector["fields"]
            frame = encode_frame(
                fields["type"], fields["sequence"], fields["payload"]
            )
            self.assertEqual(frame.decode("ascii"), vector["frame"], vector["name"])
            self.assertEqual(decode_frame(frame), fields)

    def test_crc_mismatch_is_rejected(self):
        frame = bytearray(encode_frame("PING", 3))
        frame[-2] = ord("0") if frame[-2] != ord("0") else ord("1")
        with self.assertRaisesRegex(ArmFrameError, "crc_mismatch"):
            decode_frame(frame)

    def test_fragmented_and_sticky_frames_are_recovered(self):
        decoder = FrameStreamDecoder()
        first = encode_frame("PING", 10)
        second = encode_frame("PONG", 10)
        self.assertEqual(decoder.feed(first[:5]), ([], []))
        frames, errors = decoder.feed(first[5:] + second)
        self.assertEqual(errors, [])
        self.assertEqual([frame["type"] for frame in frames], ["PING", "PONG"])

    def test_oversized_line_is_discarded_then_decoder_recovers(self):
        decoder = FrameStreamDecoder()
        frames, errors = decoder.feed(b"X" * 120 + b"\n" + encode_frame("PING", 8))
        self.assertEqual(errors, ["frame_too_long"])
        self.assertEqual(frames[0]["sequence"], 8)

    def test_motion_type_and_ping_payload_are_rejected(self):
        with self.assertRaisesRegex(ArmFrameError, "unsupported_type"):
            encode_frame("MOVE", 1)
        with self.assertRaisesRegex(ArmFrameError, "invalid_payload"):
            encode_frame("PING", 1, "data")

    def test_sequence_bounds_and_ascii_rules_are_enforced(self):
        for value in (True, 0, 2147483648):
            with self.assertRaisesRegex(ArmFrameError, "invalid_sequence"):
                encode_frame("PING", value)
        with self.assertRaisesRegex(ArmFrameError, "non_ascii_frame"):
            decode_frame(b"RPA1|PING|1||FFFF\xff\n")


if __name__ == "__main__":
    unittest.main()
