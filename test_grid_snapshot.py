import unittest
import tempfile
import os
import time
import numpy as np
from unittest.mock import patch, MagicMock

from logic.grid import BreadboardGrid
from logic.snapshot import SnapshotManager

class BreadboardGridTests(unittest.TestCase):
    def test_horizontal_board_orientation(self):
        bb_box = {'x1': 0, 'y1': 0, 'x2': 200, 'y2': 100}
        grid = BreadboardGrid(bb_box)
        self.assertTrue(grid.is_horizontal)

    def test_vertical_board_orientation(self):
        bb_box = {'x1': 0, 'y1': 0, 'x2': 100, 'y2': 200}
        grid = BreadboardGrid(bb_box)
        self.assertFalse(grid.is_horizontal)

    def test_pin_outside_board_returns_none(self):
        bb_box = {'x1': 10, 'y1': 10, 'x2': 210, 'y2': 110}
        grid = BreadboardGrid(bb_box)
        self.assertIsNone(grid.get_pin_location(5, 5))
        self.assertIsNone(grid.get_pin_location(215, 115))

    def test_pin_top_side_horizontal_board(self):
        bb_box = {'x1': 0, 'y1': 0, 'x2': 200, 'y2': 100}
        grid = BreadboardGrid(bb_box)
        pin = grid.get_pin_location(50, 20) # y < 50
        self.assertEqual(pin['side'], 'top')

    def test_pin_bottom_side_horizontal_board(self):
        bb_box = {'x1': 0, 'y1': 0, 'x2': 200, 'y2': 100}
        grid = BreadboardGrid(bb_box)
        pin = grid.get_pin_location(50, 80) # y > 50
        self.assertEqual(pin['side'], 'bottom')

    def test_row_clamped_between_1_and_30(self):
        bb_box = {'x1': 0, 'y1': 0, 'x2': 300, 'y2': 100}
        grid = BreadboardGrid(bb_box)
        pin_left = grid.get_pin_location(0, 50)
        pin_right = grid.get_pin_location(300, 50)
        self.assertGreaterEqual(pin_left['row'], 1)
        self.assertLessEqual(pin_right['row'], 30)

    def test_get_component_pins_returns_two_locations(self):
        bb_box = {'x1': 0, 'y1': 0, 'x2': 300, 'y2': 100}
        grid = BreadboardGrid(bb_box)
        comp_box = {'x1': 50, 'y1': 20, 'x2': 100, 'y2': 80}
        pin1, pin2 = grid.get_component_pins(comp_box)
        self.assertIsNotNone(pin1)
        self.assertIsNotNone(pin2)
        self.assertIn('row', pin1)
        self.assertIn('side', pin2)

class SnapshotManagerTests(unittest.TestCase):
    def test_creates_save_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            save_dir = os.path.join(tmpdir, "new_snapshots")
            self.assertFalse(os.path.exists(save_dir))
            manager = SnapshotManager(save_dir=save_dir)
            self.assertTrue(os.path.exists(save_dir))

    @patch('cv2.imwrite')
    def test_snap_on_pass_report_creates_file(self, mock_imwrite):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(save_dir=tmpdir)
            report = {'status': 'PASS', 'current_step': None, 'circuit_name': 'Test Circuit'}
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            filepath = manager.check_and_snap(report, frame)
            self.assertIsNotNone(filepath)
            self.assertTrue(filepath.endswith('.jpg'))
            self.assertIn('test_circuit_complete', filepath)
            mock_imwrite.assert_called_once_with(filepath, frame)

    @patch('cv2.imwrite')
    def test_no_snap_on_non_pass_report(self, mock_imwrite):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(save_dir=tmpdir)
            report = {'status': 'FAIL', 'circuit_name': 'Test Circuit'}
            frame = np.zeros((10, 10, 3), dtype=np.uint8)
            filepath = manager.check_and_snap(report, frame)
            self.assertIsNone(filepath)
            mock_imwrite.assert_not_called()

    @patch('cv2.imwrite')
    def test_no_snap_for_scanning_circuit(self, mock_imwrite):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(save_dir=tmpdir)
            report = {'status': 'PASS', 'circuit_name': 'scanning'}
            frame = np.zeros((10, 10, 3), dtype=np.uint8)
            filepath = manager.check_and_snap(report, frame)
            self.assertIsNone(filepath)
            mock_imwrite.assert_not_called()

    @patch('cv2.imwrite')
    def test_cooldown_prevents_rapid_snapshots(self, mock_imwrite):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SnapshotManager(save_dir=tmpdir)
            manager.last_snap_time = time.time()  # recent snapshot
            report = {'status': 'PASS'}
            frame = np.zeros((10, 10, 3), dtype=np.uint8)
            filepath = manager.check_and_snap(report, frame)
            self.assertIsNone(filepath)
            mock_imwrite.assert_not_called()

if __name__ == '__main__':
    unittest.main()
