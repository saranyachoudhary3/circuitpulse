import unittest

from logic.catalog import ComponentCatalog
from vision.layout_review import LayoutReviewError, review_layout_candidate


MODULE = {"id": "demo", "pins": [{"name": "VCC"}, {"name": "GND"}]}
CANDIDATE = {"status": "candidate", "coordinate_system": "calibration_mat_mm", "calibration_id": "a" * 64,
             "terminals": [{"pin": "VCC", "x_mm": 1, "y_mm": 1}, {"pin": "GND", "x_mm": 3, "y_mm": 1}]}


class LayoutReviewTests(unittest.TestCase):
    def test_reviewed_layout_carries_candidate_and_calibration_provenance(self):
        layout = review_layout_candidate(MODULE, CANDIDATE, "hardware-review@example.test", reviewed_at="2026-10-02T00:00:00Z")
        self.assertEqual(layout["status"], "reviewed")
        self.assertEqual(len(layout["review"]["candidate_sha256"]), 64)
        module = {**MODULE, "terminal_layout": layout}
        self.assertEqual(ComponentCatalog.terminal_layout_status(module), "REVIEWED_TERMINAL_LAYOUT")

    def test_review_rejects_pin_order_and_terminal_collisions(self):
        swapped = {**CANDIDATE, "terminals": list(reversed(CANDIDATE["terminals"]))}
        with self.assertRaises(LayoutReviewError):
            review_layout_candidate(MODULE, swapped, "reviewer")
        collision = {**CANDIDATE, "terminals": [{"pin": "VCC", "x_mm": 1, "y_mm": 1}, {"pin": "GND", "x_mm": 1.1, "y_mm": 1}]}
        with self.assertRaises(LayoutReviewError):
            review_layout_candidate(MODULE, collision, "reviewer")
