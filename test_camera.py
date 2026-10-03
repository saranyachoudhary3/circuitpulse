"""Unit tests for camera source normalization, MJPEG streaming, and health checks."""

from __future__ import annotations

import io
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from camera import CameraSourceError, VideoStreamer, normalize_camera_source


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

    @patch("cv2.VideoCapture")
    def test_streamer_usb_start_and_update(self, mock_vc):
        mock_cap = MagicMock()
        # Mock read returns True once, then False to break the loop or trigger reconnect
        mock_cap.read.side_effect = [(True, np.zeros((480, 640, 3), dtype=np.uint8)), (False, None)] * 10
        mock_vc.return_value = mock_cap
        
        streamer = VideoStreamer(src=0, width=320, height=240)
        streamer.start()
        time.sleep(0.6)
        streamer.stop()
        
        self.assertGreaterEqual(streamer.frame_count, 1)
        self.assertIsNotNone(streamer.read())
        self.assertEqual(streamer.frame.shape, (240, 320, 3))

    def test_streamer_http_resize_and_exception(self):
        class MockStream:
            def __init__(self, data):
                self.bio = io.BytesIO(data)
            def read(self, n=8192):
                chunk = self.bio.read(n)
                if not chunk:
                    streamer.stopped = True
                    raise Exception("End of stream")
                return chunk
                
        synthetic_frame = np.full((100, 100, 3), 200, dtype=np.uint8)
        _, jpeg_bytes = cv2.imencode(".jpg", synthetic_frame)
        raw_jpeg = bytes(jpeg_bytes)
        
        streamer = object.__new__(VideoStreamer)
        streamer.src = "http://127.0.0.1:8080/video"
        streamer.is_http = True
        streamer.actual_width = 50
        streamer.actual_height = 50
        streamer.stopped = False
        streamer.lock = threading.Lock()
        streamer.frame = None
        streamer.ret = False
        streamer.frame_count = 1
        streamer.reconnect_count = 0
        streamer.last_frame_monotonic = None
        streamer.stream = None
        
        with patch("urllib.request.urlopen", return_value=MockStream(raw_jpeg + b"x"*600000)):
            streamer.update()
            
        self.assertFalse(streamer.ret)

    def test_read_max_age_none(self):
        streamer = object.__new__(VideoStreamer)
        streamer.lock = threading.Lock()
        streamer.frame = np.zeros((10, 10, 3), dtype=np.uint8)
        self.assertIsNotNone(streamer.read(max_age_seconds=None))

if __name__ == "__main__":
    unittest.main()
