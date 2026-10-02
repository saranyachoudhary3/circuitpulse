import unittest
from logic.grid import BreadboardGrid

class TestBreadboardGrid(unittest.TestCase):
    def setUp(self):
        self.grid = BreadboardGrid([0, 0, 640, 480])

    # Power rail tests
    def test_top_power_rail_positive(self):
        pin = self.grid.get_pin_location(100, 10)  # top-left area
        self.assertTrue(pin["is_power_rail"])
        self.assertEqual(pin["side"], "top_rail")

    def test_bottom_power_rail(self):
        pin = self.grid.get_pin_location(100, 470)
        self.assertTrue(pin["is_power_rail"])

    # Center gap tests
    def test_center_gap_isolation(self):
        pin = self.grid.get_pin_location(320, 240)  # dead center
        self.assertEqual(pin["side"], "center")
        self.assertEqual(pin["column"], "gap")

    # Same electrical node tests
    def test_same_row_same_side_connected(self):
        pin1 = self.grid.get_pin_location(50, 240)   # left side
        pin2 = self.grid.get_pin_location(100, 240)  # left side
        self.assertTrue(self.grid.same_electrical_node(pin1, pin2))

    def test_same_row_different_side_not_connected(self):
        pin1 = self.grid.get_pin_location(50, 240)   # left side
        pin2 = self.grid.get_pin_location(550, 240)  # right side
        self.assertFalse(self.grid.same_electrical_node(pin1, pin2))

    def test_different_row_same_side_not_connected(self):
        pin1 = self.grid.get_pin_location(50, 200)
        pin2 = self.grid.get_pin_location(50, 300)
        self.assertFalse(self.grid.same_electrical_node(pin1, pin2))

    # Column detection
    def test_left_side_column_a(self):
        pin = self.grid.get_pin_location(10, 240)
        self.assertIn(pin["column"], "abcde")
        self.assertEqual(pin["side"], "left")

    def test_right_side_column_f_to_j(self):
        pin = self.grid.get_pin_location(600, 240)
        self.assertIn(pin["column"], "fghij")
        self.assertEqual(pin["side"], "right")

    # Connected components grouping
    def test_connected_components_groups_same_row(self):
        pins = [
            self.grid.get_pin_location(50, 240),
            self.grid.get_pin_location(100, 240),
            self.grid.get_pin_location(50, 300),  # different row
        ]
        groups = self.grid.connected_components(pins)
        self.assertEqual(len(groups), 2)  # two groups

    # Power rail connectivity
    def test_same_power_rail_connected(self):
        pin1 = self.grid.get_pin_location(50, 10)
        pin2 = self.grid.get_pin_location(200, 10)
        self.assertTrue(self.grid.same_electrical_node(pin1, pin2))

    def test_different_power_rails_not_connected(self):
        pin1 = self.grid.get_pin_location(50, 10)   # top rail
        pin2 = self.grid.get_pin_location(50, 470)  # bottom rail
        self.assertFalse(self.grid.same_electrical_node(pin1, pin2))

    def test_power_rail_not_connected_to_main(self):
        pin1 = self.grid.get_pin_location(50, 10)   # power rail
        pin2 = self.grid.get_pin_location(50, 240)  # main area
        self.assertFalse(self.grid.same_electrical_node(pin1, pin2))

    # Row range
    def test_row_range_valid(self):
        pin = self.grid.get_pin_location(50, 240)
        self.assertGreaterEqual(pin["row"], 1)
        self.assertLessEqual(pin["row"], 30)

    # Invalid bbox
    def test_zero_dimension_bbox_raises(self):
        with self.assertRaises(ValueError):
            BreadboardGrid([100, 100, 100, 100])  # zero width

    # Center gap pin is isolated
    def test_center_gap_not_connected_to_anything(self):
        center = self.grid.get_pin_location(320, 240)
        left = self.grid.get_pin_location(50, 240)
        right = self.grid.get_pin_location(550, 240)
        self.assertFalse(self.grid.same_electrical_node(center, left))
        self.assertFalse(self.grid.same_electrical_node(center, right))

if __name__ == '__main__':
    unittest.main()
