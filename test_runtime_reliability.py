import time
import threading
import unittest

import numpy as np

from camera import VideoStreamer, normalize_camera_source


class CaptureFreshnessTests(unittest.TestCase):
    def test_ip_webcam_host_port_is_normalized_to_mjpeg_video_endpoint(self):
        self.assertEqual(normalize_camera_source("192.0.0.4:8080"), "http://192.0.0.4:8080/video")
        self.assertEqual(normalize_camera_source("http://192.0.0.4:8080"), "http://192.0.0.4:8080/video")
        self.assertEqual(normalize_camera_source("rtsp://camera.local/live"), "rtsp://camera.local/live")

    @staticmethod
    def _streamer_with_frame(age_seconds):
        # Unit-test freshness without opening a physical camera device.
        streamer = object.__new__(VideoStreamer)
        streamer.lock = threading.Lock()
        streamer.frame = np.zeros((4, 4, 3), dtype=np.uint8)
        streamer.last_frame_monotonic = time.monotonic() - age_seconds
        streamer.frame_count = 1
        streamer.reconnect_count = 0
        return streamer

    def test_stale_frame_is_not_returned_as_live_evidence(self):
        streamer = self._streamer_with_frame(2)
        self.assertIsNone(streamer.read(max_age_seconds=1.0))
        self.assertEqual(streamer.health(max_age_seconds=1.0)["status"], "STALE")

    def test_fresh_frame_is_available(self):
        streamer = self._streamer_with_frame(0)
        self.assertIsNotNone(streamer.read(max_age_seconds=1.0))
        self.assertEqual(streamer.health(max_age_seconds=1.0)["status"], "READY")


if __name__ == "__main__":
    unittest.main()
