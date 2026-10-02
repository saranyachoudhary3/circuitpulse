"""Optional live Raspberry Pi detector integration test.

This module deliberately makes no network request during import or normal test
discovery. Set ``CIRCUITPULSE_PI_URL`` and ``CIRCUITPULSE_PI_IMAGE`` to run it
against a specifically prepared Pi deployment.
"""

from __future__ import annotations

import os
from pathlib import Path
import unittest

import requests


PI_URL = os.environ.get("CIRCUITPULSE_PI_URL")
PI_IMAGE = os.environ.get("CIRCUITPULSE_PI_IMAGE")


@unittest.skipUnless(PI_URL and PI_IMAGE, "Set CIRCUITPULSE_PI_URL and CIRCUITPULSE_PI_IMAGE to run live Pi integration.")
class PiIntegrationTests(unittest.TestCase):
    def test_detector_accepts_a_real_image(self):
        image = Path(PI_IMAGE)
        self.assertTrue(image.is_file(), f"Pi test image does not exist: {image}")
        with image.open("rb") as source:
            response = requests.post(f"{PI_URL.rstrip('/')}/api/detect", files={"image": source}, timeout=10)
        response.raise_for_status()
        payload = response.json()
        self.assertIsInstance(payload.get("detections"), list)
        self.assertIsInstance(payload.get("num_detections"), int)


if __name__ == "__main__":
    unittest.main()
