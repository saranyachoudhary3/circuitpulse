"""Unit tests for CircuitPulse v2 vision and detector modules.

Covers:
- detectors/resistor.py: ResistorDecoder, classify_pixel_color, snap_to_e12, format_ohms
- detectors/wires.py: WireTracer endpoint extraction, color thresholds, boundary handling
- detectors/tracker.py: Tracker IoU, coordinate EMA smoothing, confidence blending, track lifecycle
- detectors/zoom.py: AutoZoom breadboard centering, margin expansion, min-size guard, coordinate translation
- detectors/memory.py: WireMemory temporal persistence, uncrossed endpoint EMA, hysteresis
- camera.py: normalize_camera_source, VideoStreamer MJPEG parsing, freshness, health reporting
- vision/wire_masks.py: WireMaskExtractor binary mask endpoint extraction and rejection
"""

from __future__ import annotations

import io
import math
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from camera import CameraSourceError, VideoStreamer, normalize_camera_source
from detectors.memory import WireMemory
from detectors.resistor import (
    COLOR_DIGITS,
    COLOR_MULTIPLIERS,
    COLOR_TOLERANCES,
    STANDARD_E12,
    ResistorDecoder,
    classify_pixel_color,
    format_ohms,
    snap_to_e12,
)
from detectors.tracker import Tracker
from detectors.wires import WireTracer
from detectors.zoom import AutoZoom
from vision.wire_masks import WireMaskExtractor


class TestResistorDecoder(unittest.TestCase):
    """Unit tests for resistor color classification, decoding, and formatting."""

    def test_classify_pixel_color_all_bands(self):
        """Verify HSV classification across all recognized resistor bands and body tones."""
        color_samples = {
            "black": [10, 10, 10],
            "white": [240, 240, 240],
            "gray": [100, 100, 100],
            "red": [0, 0, 220],
            "orange": [110, 130, 170],
            "yellow": [94, 130, 130],
            "green": [0, 200, 0],
            "blue": [220, 0, 0],
            "violet": [70, 56, 61],
            "brown": [56, 61, 70],
            "gold": [105, 120, 130],
            "body": [137, 148, 170],
        }

        for expected_label, bgr in color_samples.items():
            actual_label = classify_pixel_color(bgr)
            self.assertEqual(
                actual_label,
                expected_label,
                f"BGR pixel {bgr} classified as '{actual_label}', expected '{expected_label}'",
            )

    def test_resistor_decoder_standard_4band_220_ohm(self):
        """Verify end-to-end decoding of a synthetic 4-band resistor crop (Red-Red-Brown-Gold = 220 Ω, 5%)."""
        crop = np.full((30, 100, 3), [137, 148, 170], dtype=np.uint8)
        # Band 1: Red (2)
        crop[:, 20:27] = [0, 0, 220]
        # Band 2: Red (2)
        crop[:, 35:42] = [0, 0, 220]
        # Band 3: Brown (multiplier 10)
        crop[:, 50:57] = [56, 61, 70]
        # Band 4: Gold (tolerance 5%)
        crop[:, 70:77] = [105, 120, 130]

        decoder = ResistorDecoder()
        result = decoder.decode(crop)

        self.assertIsNotNone(result, "ResistorDecoder returned None for valid 220Ω synthetic crop")
        self.assertEqual(result["ohms"], 220)
        self.assertEqual(result["formatted"], "220 5%")
        self.assertEqual(result["raw_value"], "220")
        self.assertEqual(result["bands"], ["red", "red", "brown", "gold"])
        self.assertGreater(result["decode_confidence"], 0.5)

    def test_resistor_decoder_orientation_and_reversal(self):
        """Verify automatic 90-degree rotation when H > W, and automatic band reversal when Gold is first."""
        base_crop = np.full((30, 100, 3), [137, 148, 170], dtype=np.uint8)
        base_crop[:, 20:27] = [0, 0, 220]
        base_crop[:, 35:42] = [0, 0, 220]
        base_crop[:, 50:57] = [56, 61, 70]
        base_crop[:, 70:77] = [105, 120, 130]

        # Subtest A: Vertical crop (height > width)
        vertical_crop = cv2.rotate(base_crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
        self.assertGreater(vertical_crop.shape[0], vertical_crop.shape[1])
        res_vertical = ResistorDecoder().decode(vertical_crop)
        self.assertIsNotNone(res_vertical)
        self.assertEqual(res_vertical["ohms"], 220)
        self.assertEqual(res_vertical["formatted"], "220 5%")

        # Subtest B: Reversed bands (Gold first on the left)
        reversed_crop = np.full((30, 100, 3), [137, 148, 170], dtype=np.uint8)
        reversed_crop[:, 20:27] = [105, 120, 130]  # Gold
        reversed_crop[:, 40:47] = [56, 61, 70]    # Brown
        reversed_crop[:, 55:62] = [0, 0, 220]      # Red
        reversed_crop[:, 70:77] = [0, 0, 220]      # Red

        res_reversed = ResistorDecoder().decode(reversed_crop)
        self.assertIsNotNone(res_reversed)
        self.assertEqual(res_reversed["ohms"], 220)
        self.assertEqual(res_reversed["formatted"], "220 5%")
        self.assertEqual(res_reversed["bands"], ["red", "red", "brown", "gold"])

    def test_resistor_decoder_edge_cases_and_helpers(self):
        """Verify helper functions snap_to_e12, format_ohms, and invalid crop rejection."""
        decoder = ResistorDecoder()

        # Crop validation edge cases
        self.assertIsNone(decoder.decode(None))
        self.assertIsNone(decoder.decode(np.zeros((5, 10, 3), dtype=np.uint8)))
        self.assertIsNone(decoder.decode(np.zeros((8, 14, 3), dtype=np.uint8)))
        self.assertIsNone(decoder.decode(np.full((30, 100, 3), [137, 148, 170], dtype=np.uint8)))

        # snap_to_e12
        self.assertEqual(snap_to_e12(215), 220)
        self.assertEqual(snap_to_e12(4600), 4700)
        self.assertEqual(snap_to_e12(10), 10)
        self.assertEqual(snap_to_e12(1000000), 1000000)
        self.assertEqual(snap_to_e12(-10), 220)
        self.assertEqual(snap_to_e12(0), 220)

        # format_ohms
        self.assertEqual(format_ohms(220, "5%"), ("220 5%", "220"))
        self.assertEqual(format_ohms(4700, "1%"), ("4.7k 1%", "4.7k"))
        self.assertEqual(format_ohms(1000000, "2%"), ("1M 2%", "1M"))
        self.assertEqual(format_ohms(10), ("10 5%", "10"))


class TestWireTracer(unittest.TestCase):
    """Unit tests for wire skeleton endpoint extraction and HSV thresholds."""

    def test_wire_tracer_clean_diagonal_wire(self):
        """Verify skeleton endpoint extraction of a red wire on neutral gray background.

        CRITICAL: Background must be neutral gray [128, 128, 128] to avoid the OpenCV
        border-replication infinite loop hazard documented in survey findings.
        """
        frame = np.full((100, 100, 3), 128, dtype=np.uint8)
        cv2.line(frame, (25, 25), (75, 75), (0, 0, 255), thickness=3)
        bbox = {"x1": 20, "y1": 20, "x2": 80, "y2": 80}

        ep1, ep2 = WireTracer.get_endpoints(frame, bbox)

        self.assertIsNotNone(ep1)
        self.assertIsNotNone(ep2)

        # Check endpoints are within 5 pixels of the drawn line tips (25, 25) and (75, 75)
        d1_start = math.hypot(ep1[0] - 25, ep1[1] - 25)
        d1_end = math.hypot(ep1[0] - 75, ep1[1] - 75)
        d2_start = math.hypot(ep2[0] - 25, ep2[1] - 25)
        d2_end = math.hypot(ep2[0] - 75, ep2[1] - 75)

        paired_direct = (d1_start <= 5.0 and d2_end <= 5.0)
        paired_inverted = (d2_start <= 5.0 and d1_end <= 5.0)
        self.assertTrue(
            paired_direct or paired_inverted,
            f"Extracted endpoints {ep1}, {ep2} not within 5px of (25, 25) and (75, 75)",
        )

    def test_wire_tracer_multi_color_support(self):
        """Verify endpoint extraction across blue, green, and yellow wire colors."""
        colors = {
            "blue": (255, 0, 0),
            "green": (0, 200, 0),
            "yellow": (0, 255, 255),
        }

        for color_name, bgr in colors.items():
            frame = np.full((100, 100, 3), 128, dtype=np.uint8)
            cv2.line(frame, (20, 30), (80, 70), bgr, thickness=3)
            bbox = {"x1": 15, "y1": 25, "x2": 85, "y2": 75}

            ep1, ep2 = WireTracer.get_endpoints(frame, bbox)
            self.assertIsNotNone(ep1, f"Failed endpoint 1 for color {color_name}")
            self.assertIsNotNone(ep2, f"Failed endpoint 2 for color {color_name}")

            # Endpoints should match line terminals near (20, 30) and (80, 70)
            d1_start = math.hypot(ep1[0] - 20, ep1[1] - 30)
            d1_end = math.hypot(ep1[0] - 80, ep1[1] - 70)
            d2_start = math.hypot(ep2[0] - 20, ep2[1] - 30)
            d2_end = math.hypot(ep2[0] - 80, ep2[1] - 70)

            paired = (d1_start <= 6.0 and d2_end <= 6.0) or (d2_start <= 6.0 and d1_end <= 6.0)
            self.assertTrue(paired, f"Color {color_name} endpoints {ep1}, {ep2} mismatched")

    def test_wire_tracer_empty_out_of_bounds_and_canny_fallback(self):
        """Verify out-of-bounds crops, zero crops, and uniform frame handling."""
        frame = np.full((100, 100, 3), 128, dtype=np.uint8)

        # 1. Out of bounds crop
        ep1, ep2 = WireTracer.get_endpoints(frame, {"x1": 150, "y1": 150, "x2": 160, "y2": 160})
        self.assertIsNone(ep1)
        self.assertIsNone(ep2)

        # 2. Clamped zero-size crop
        ep1, ep2 = WireTracer.get_endpoints(frame, {"x1": -20, "y1": -20, "x2": 0, "y2": 0})
        self.assertIsNone(ep1)
        self.assertIsNone(ep2)

        # 3. Uniform frame with no wire features
        ep1, ep2 = WireTracer.get_endpoints(frame, {"x1": 20, "y1": 20, "x2": 50, "y2": 50})
        self.assertIsNone(ep1)
        self.assertIsNone(ep2)


class TestTracker(unittest.TestCase):
    """Unit tests for bounding box tracking, EMA smoothing, and track lifecycle."""

    def test_tracker_iou_calculation(self):
        """Verify mathematical correctness of Tracker._iou()."""
        tracker = Tracker()
        b1 = {"x1": 0, "y1": 0, "x2": 10, "y2": 10}

        # Identical box
        self.assertEqual(tracker._iou(b1, b1), 1.0)

        # Disjoint box
        b2 = {"x1": 20, "y1": 20, "x2": 30, "y2": 30}
        self.assertEqual(tracker._iou(b1, b2), 0.0)

        # Partial overlap (50% overlap of b1 with identical height)
        # b1: 0..10 x 0..10 (area 100)
        # b3: 5..15 x 0..10 (area 100)
        # inter: 5..10 x 0..10 (area 50), union: 150 -> IoU = 50/150 = 1/3
        b3 = {"x1": 5, "y1": 0, "x2": 15, "y2": 10}
        self.assertAlmostEqual(tracker._iou(b1, b3), 1.0 / 3.0, places=3)

        # Zero area box
        b4 = {"x1": 0, "y1": 0, "x2": 0, "y2": 0}
        self.assertEqual(tracker._iou(b1, b4), 0.0)

    def test_tracker_ema_smoothing_and_confidence_blending(self):
        """Verify coordinate EMA formula (alpha=0.65) and confidence blending."""
        tracker = Tracker(alpha=0.65, iou_thresh=0.38, max_missing=3)

        frame1 = [{"class": "resistor", "confidence": 0.8, "bbox": {"x1": 10, "y1": 10, "x2": 50, "y2": 50}}]
        out1 = tracker.update(frame1)
        self.assertEqual(len(out1), 1)
        self.assertEqual(out1[0]["bbox"], {"x1": 10, "y1": 10, "x2": 50, "y2": 50})
        self.assertEqual(out1[0]["confidence"], 0.8)

        # Frame 2: slightly shifted box
        frame2 = [{"class": "resistor", "confidence": 0.9, "bbox": {"x1": 14, "y1": 14, "x2": 54, "y2": 54}}]
        out2 = tracker.update(frame2)
        self.assertEqual(len(out2), 1)

        # Expected EMA:
        # x1 = int(0.65 * 14 + 0.35 * 10) = int(9.1 + 3.5) = 12
        # confidence = round(0.7 * 0.9 + 0.3 * 0.8, 3) = 0.87
        self.assertEqual(out2[0]["bbox"]["x1"], 12)
        self.assertEqual(out2[0]["bbox"]["y1"], 12)
        self.assertEqual(out2[0]["bbox"]["x2"], 52)
        self.assertEqual(out2[0]["bbox"]["y2"], 52)
        self.assertEqual(out2[0]["confidence"], 0.87)

    def test_tracker_track_persistence_and_pruning(self):
        """Verify tracks persist up to max_missing frames and are pruned when exceeded."""
        tracker = Tracker(alpha=0.65, iou_thresh=0.38, max_missing=3)

        # Frame 1: Register track
        f1 = [{"class": "resistor", "confidence": 0.85, "bbox": {"x1": 10, "y1": 10, "x2": 50, "y2": 50}}]
        tracker.update(f1)
        self.assertEqual(len(tracker.tracks), 1)

        # Frame 2: Missing (missing = 1 <= 3)
        out2 = tracker.update([])
        self.assertEqual(len(out2), 0)
        self.assertEqual(len(tracker.tracks), 1)
        self.assertEqual(tracker.tracks[1]["missing"], 1)

        # Frame 3: Missing (missing = 2 <= 3)
        out3 = tracker.update([])
        self.assertEqual(len(out3), 0)
        self.assertEqual(len(tracker.tracks), 1)
        self.assertEqual(tracker.tracks[1]["missing"], 2)

        # Frame 4: Missing (missing = 3 <= 3)
        out4 = tracker.update([])
        self.assertEqual(len(out4), 0)
        self.assertEqual(len(tracker.tracks), 1)
        self.assertEqual(tracker.tracks[1]["missing"], 3)

        # Frame 5: Missing (missing = 4 > 3 -> pruned)
        out5 = tracker.update([])
        self.assertEqual(len(out5), 0)
        self.assertEqual(len(tracker.tracks), 0)

    def test_tracker_class_isolation_and_multi_detection(self):
        """Verify tracker isolates tracks by class even with overlapping bounding boxes."""
        tracker = Tracker(alpha=0.65, iou_thresh=0.38, max_missing=3)

        box1 = {"class": "resistor", "confidence": 0.9, "bbox": {"x1": 10, "y1": 10, "x2": 50, "y2": 50}}
        box2 = {"class": "wire", "confidence": 0.85, "bbox": {"x1": 10, "y1": 10, "x2": 50, "y2": 50}}

        out = tracker.update([box1, box2])
        self.assertEqual(len(out), 2)
        self.assertEqual(len(tracker.tracks), 2)

        classes = {t["class"] for t in tracker.tracks.values()}
        self.assertEqual(classes, {"resistor", "wire"})


class TestAutoZoom(unittest.TestCase):
    """Unit tests for PTZ Auto-Zoom centering, margins, and coordinate translation."""

    def test_auto_zoom_breadboard_margin_and_coordinate_translation(self):
        """Verify breadboard margin expansion, crop shape, and coordinate translation."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        az = AutoZoom(alpha=0.5, margin=0.3)

        detections = [
            {"class": "breadboard", "bbox": {"x1": 200, "y1": 100, "x2": 400, "y2": 300}},
            {
                "class": "wire",
                "bbox": {"x1": 220, "y1": 120, "x2": 260, "y2": 160},
                "endpoints": [[225, 125], [255, 155]],
            },
        ]

        # bw = 200, bh = 200. margin = 60px.
        # target = [140, 40, 460, 360], size = 320x320
        cropped_frame, translated_detections = az.process(frame, detections)

        self.assertEqual(cropped_frame.shape, (320, 320, 3))
        self.assertEqual(az.current_crop, [140, 40, 460, 360])

        wire_trans = next(d for d in translated_detections if d["class"] == "wire")
        self.assertEqual(wire_trans["bbox"], {"x1": 80, "y1": 80, "x2": 120, "y2": 120})
        self.assertEqual(wire_trans["endpoints"], [[85, 85], [115, 115]])

    def test_auto_zoom_no_breadboard_and_min_size_guard(self):
        """Verify fallback to full frame when no breadboard exists or size < 100px."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # 1. No breadboard detection
        az1 = AutoZoom(alpha=0.1, margin=0.3)
        crop1, trans1 = az1.process(frame, [])
        self.assertEqual(crop1.shape, (480, 640, 3))
        self.assertEqual(az1.current_crop, [0, 0, 640, 480])

        # 2. Tiny breadboard (< 100px) triggers min-size guard reset
        az2 = AutoZoom(alpha=0.1, margin=0.3)
        tiny_bb = [{"class": "breadboard", "bbox": {"x1": 10, "y1": 10, "x2": 50, "y2": 50}}]
        crop2, trans2 = az2.process(frame, tiny_bb)
        self.assertEqual(crop2.shape, (480, 640, 3))
        self.assertEqual(az2.current_crop, [0, 0, 640, 480])

    def test_auto_zoom_ema_transition_and_boundary_clamping(self):
        """Verify smooth EMA crop transition across consecutive frames and boundary clamping."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        az = AutoZoom(alpha=0.5, margin=0.0)

        # Frame 1: Initial breadboard at [100, 100, 300, 300]
        bb1 = [{"class": "breadboard", "bbox": {"x1": 100, "y1": 100, "x2": 300, "y2": 300}}]
        az.process(frame, bb1)
        self.assertEqual(az.current_crop, [100, 100, 300, 300])

        # Frame 2: Breadboard moves to [200, 200, 400, 400]
        # EMA with alpha=0.5: crop moves to [150, 150, 350, 350]
        bb2 = [{"class": "breadboard", "bbox": {"x1": 200, "y1": 200, "x2": 400, "y2": 400}}]
        crop2, _ = az.process(frame, bb2)
        self.assertEqual(az.current_crop, [150, 150, 350, 350])
        self.assertEqual(crop2.shape, (200, 200, 3))


class TestWireMemory(unittest.TestCase):
    """Unit tests for wire temporal persistence, hysteresis, and uncrossing logic."""

    def test_wire_memory_temporal_persistence_and_uncrossed_ema(self):
        """Verify occluded endpoints are restored and inverted endpoints are uncrossed."""
        mem = WireMemory(max_missing=3, movement_thresh=20)

        # Frame 1: Initial wire detection with endpoints
        f1 = [
            {
                "class": "wire",
                "bbox": {"x1": 10, "y1": 10, "x2": 50, "y2": 50},
                "endpoints": [[12, 12], [48, 48]],
            }
        ]
        out1 = mem.update(f1)
        self.assertEqual(out1[0]["endpoints"], [[12, 12], [48, 48]])
        self.assertEqual(mem.tracks[1]["missing"], 0)

        # Frame 2: Wire detected but endpoints lost (e.g. glare/occlusion)
        f2 = [{"class": "wire", "bbox": {"x1": 11, "y1": 11, "x2": 51, "y2": 51}}]
        out2 = mem.update(f2)
        self.assertEqual(out2[0]["endpoints"], [[12, 12], [48, 48]])
        self.assertEqual(mem.tracks[1]["missing"], 1)

        # Frame 3: Endpoints detected in reverse order [[50, 50], [10, 10]]
        # Distance uncrossing pairs [12, 12] with [10, 10] and [48, 48] with [50, 50]
        # EMA alpha=0.3:
        # e0 = int(12*0.7 + 10*0.3) = 11
        # e1 = int(48*0.7 + 50*0.3) = 48
        f3 = [
            {
                "class": "wire",
                "bbox": {"x1": 10, "y1": 10, "x2": 50, "y2": 50},
                "endpoints": [[50, 50], [10, 10]],
            }
        ]
        out3 = mem.update(f3)
        self.assertEqual(out3[0]["endpoints"], [[11, 11], [48, 48]])
        self.assertEqual(mem.tracks[1]["missing"], 0)

    def test_wire_memory_track_pruning(self):
        """Verify stale wire tracks are purged after max_missing frames."""
        mem = WireMemory(max_missing=3, movement_thresh=20)

        f1 = [
            {
                "class": "wire",
                "bbox": {"x1": 10, "y1": 10, "x2": 50, "y2": 50},
                "endpoints": [[12, 12], [48, 48]],
            }
        ]
        mem.update(f1)
        self.assertEqual(len(mem.tracks), 1)

        mem.update([])
        self.assertEqual(len(mem.tracks), 1)
        self.assertEqual(mem.tracks[1]["missing"], 1)

        mem.update([])
        self.assertEqual(len(mem.tracks), 1)
        self.assertEqual(mem.tracks[1]["missing"], 2)

        mem.update([])
        self.assertEqual(len(mem.tracks), 1)
        self.assertEqual(mem.tracks[1]["missing"], 3)

        mem.update([])
        self.assertEqual(len(mem.tracks), 0)

    def test_wire_memory_movement_threshold_and_non_wire_filtering(self):
        """Verify jump greater than movement_thresh creates a new track, ignoring non-wires."""
        mem = WireMemory(max_missing=3, movement_thresh=20)

        # Wire and resistor
        f1 = [
            {
                "class": "wire",
                "bbox": {"x1": 10, "y1": 10, "x2": 50, "y2": 50},
                "endpoints": [[12, 12], [48, 48]],
            },
            {
                "class": "resistor",
                "bbox": {"x1": 20, "y1": 20, "x2": 60, "y2": 60},
            },
        ]
        mem.update(f1)
        self.assertEqual(len(mem.tracks), 1)

        # Wire jumps 100 pixels away
        f2 = [
            {
                "class": "wire",
                "bbox": {"x1": 120, "y1": 120, "x2": 160, "y2": 160},
                "endpoints": [[122, 122], [158, 158]],
            }
        ]
        mem.update(f2)
        self.assertEqual(len(mem.tracks), 2)
        self.assertEqual(mem.tracks[1]["missing"], 1)
        self.assertEqual(mem.tracks[2]["missing"], 0)


class TestCamera(unittest.TestCase):
    """Unit tests for camera source normalization, MJPEG streaming, and health checks."""

    def test_normalize_camera_source_valid_inputs(self):
        """Verify normalization of camera sources across USB, IP Webcam, and RTSP."""
        self.assertEqual(normalize_camera_source(0), 0)
        self.assertEqual(normalize_camera_source("1"), 1)
        self.assertEqual(normalize_camera_source("10.0.0.5:8080"), "http://10.0.0.5:8080/video")
        self.assertEqual(normalize_camera_source("http://10.0.0.5:8080/"), "http://10.0.0.5:8080/video")
        self.assertEqual(
            normalize_camera_source("http://10.0.0.5:8080/custom_feed"),
            "http://10.0.0.5:8080/custom_feed",
        )
        self.assertEqual(normalize_camera_source("rtsp://10.0.0.5:554/live"), "rtsp://10.0.0.5:554/live")

    def test_normalize_camera_source_invalid_inputs(self):
        """Verify invalid camera sources raise CameraSourceError."""
        invalid_sources = ["", "   ", None, "http://", [], 3.14]
        for src in invalid_sources:
            with self.assertRaises(CameraSourceError):
                normalize_camera_source(src)

    def test_streamer_mjpeg_parsing_and_frame_freshness(self):
        """Verify VideoStreamer MJPEG stream parsing and health reporting without real network."""
        synthetic_frame = np.full((100, 100, 3), 200, dtype=np.uint8)
        synthetic_frame[20:80, 20:80] = [0, 0, 255]
        _, jpeg_bytes = cv2.imencode(".jpg", synthetic_frame)
        raw_jpeg = bytes(jpeg_bytes)

        streamer = object.__new__(VideoStreamer)
        streamer.src = "http://127.0.0.1:8080/video"
        streamer.is_http = True
        streamer.actual_width = 100
        streamer.actual_height = 100
        streamer.stopped = False
        streamer.lock = threading.Lock()
        streamer.frame = None
        streamer.ret = False
        streamer.frame_count = 0
        streamer.reconnect_count = 0
        streamer.last_frame_monotonic = None
        streamer.stream = None

        class MockStream:
            def __init__(self, data):
                self.bio = io.BytesIO(data)

            def read(self, n=8192):
                chunk = self.bio.read(n)
                if not chunk:
                    streamer.stopped = True
                return chunk

        with patch("urllib.request.urlopen", return_value=MockStream(raw_jpeg)):
            streamer.update()

        self.assertEqual(streamer.frame_count, 1)
        self.assertEqual(streamer.frame.shape, (100, 100, 3))
        self.assertIsNotNone(streamer.read())
        health = streamer.health(max_age_seconds=1.0)
        self.assertEqual(health["status"], "READY")
        self.assertEqual(health["frame_count"], 1)

    def test_streamer_mjpeg_orphan_end_marker_recovery(self):
        """Verify VideoStreamer recovers from mid-stream orphan end markers (b'\\xff\\xd9')."""
        synthetic_frame = np.full((80, 80, 3), 150, dtype=np.uint8)
        _, jpeg_bytes = cv2.imencode(".jpg", synthetic_frame)
        raw_jpeg = bytes(jpeg_bytes)

        # Corrupt prefix with orphan end marker before valid start marker
        corrupted_stream = b"garbage_prefix\xff\xd9more_garbage" + raw_jpeg

        streamer = object.__new__(VideoStreamer)
        streamer.src = "http://127.0.0.1:8080/video"
        streamer.is_http = True
        streamer.actual_width = 80
        streamer.actual_height = 80
        streamer.stopped = False
        streamer.lock = threading.Lock()
        streamer.frame = None
        streamer.ret = False
        streamer.frame_count = 0
        streamer.reconnect_count = 0
        streamer.last_frame_monotonic = None
        streamer.stream = None

        class MockStream:
            def __init__(self, data):
                self.bio = io.BytesIO(data)

            def read(self, n=8192):
                chunk = self.bio.read(n)
                if not chunk:
                    streamer.stopped = True
                return chunk

        with patch("urllib.request.urlopen", return_value=MockStream(corrupted_stream)):
            streamer.update()

        self.assertEqual(streamer.frame_count, 1)
        self.assertIsNotNone(streamer.frame)
        self.assertEqual(streamer.frame.shape, (80, 80, 3))

    def test_streamer_freshness_and_health_stale(self):
        """Verify frame freshness checks return None and report STALE for expired frames."""
        streamer = object.__new__(VideoStreamer)
        streamer.lock = threading.Lock()
        streamer.frame = np.zeros((10, 10, 3), dtype=np.uint8)
        streamer.last_frame_monotonic = time.monotonic() - 5.0
        streamer.frame_count = 1
        streamer.reconnect_count = 0

        self.assertIsNone(streamer.read(max_age_seconds=1.0))
        health = streamer.health(max_age_seconds=1.0)
        self.assertEqual(health["status"], "STALE")
        self.assertGreater(health["frame_age_seconds"], 4.0)

    def test_streamer_stop_releases_resources(self):
        """Verify streamer stop sets stopped flag and releases capture handle."""
        streamer = object.__new__(VideoStreamer)
        streamer.stopped = False
        mock_capture = MagicMock()
        streamer.stream = mock_capture

        streamer.stop()
        self.assertTrue(streamer.stopped)
        mock_capture.release.assert_called_once()


class TestWireMaskExtractor(unittest.TestCase):
    """Unit tests for instance segmentation wire mask extraction."""

    def test_wire_mask_extractor_empty_and_small(self):
        """Verify empty and sub-threshold masks are rejected as AMBIGUOUS."""
        extractor = WireMaskExtractor()

        # None mask
        r_none = extractor.extract(None)
        self.assertEqual(r_none["status"], "AMBIGUOUS")
        self.assertEqual(r_none["reason"], "empty_mask")

        # Zero size mask
        r_empty = extractor.extract(np.zeros((0, 0), dtype=np.uint8))
        self.assertEqual(r_empty["status"], "AMBIGUOUS")
        self.assertEqual(r_empty["reason"], "empty_mask")

        # Sub-threshold non-zero count (< 12 pixels)
        small_mask = np.zeros((50, 50), dtype=np.uint8)
        small_mask[10:13, 10:13] = 255  # 9 pixels
        r_small = extractor.extract(small_mask)
        self.assertEqual(r_small["status"], "AMBIGUOUS")
        self.assertEqual(r_small["reason"], "mask_too_small")

    def test_wire_mask_extractor_clean_line(self):
        """Verify clean single wire mask is identified as CANDIDATE with 2 endpoints."""
        extractor = WireMaskExtractor()
        mask = np.zeros((100, 100), dtype=np.uint8)
        cv2.line(mask, (10, 10), (90, 90), 255, thickness=2)

        result = extractor.extract(mask)
        self.assertEqual(result["status"], "CANDIDATE")
        self.assertEqual(len(result["endpoints"]), 2)
        self.assertGreater(result["confidence"], 0.5)


if __name__ == "__main__":
    unittest.main()
