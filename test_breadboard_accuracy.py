import unittest

from logic.grid import BreadboardGrid


class TestBreadboardAccuracy(unittest.TestCase):
    def setUp(self):
        # Full box from 0,0 to 100,100
        self.grid = BreadboardGrid([0.0, 0.0, 100.0, 100.0], rows=30)

    def test_left_columns_a_to_e(self):
        # 5 columns mapped within 0 to 0.44.
        # Let's test the center of each column roughly
        y = 50.0  # middle of board
        for i, col in enumerate(['a', 'b', 'c', 'd', 'e']):
            x = (i + 0.5) * (44.0 / 5)
            pin = self.grid.get_pin_location(x, y)
            self.assertEqual(pin["column"], col)
            self.assertEqual(pin["side"], "left")

    def test_right_columns_f_to_j(self):
        y = 50.0
        # Right side starts at 0.56, span 0.44
        for i, col in enumerate(['f', 'g', 'h', 'i', 'j']):
            x = 56.0 + (i + 0.5) * (44.0 / 5)
            pin = self.grid.get_pin_location(x, y)
            self.assertEqual(pin["column"], col)
            self.assertEqual(pin["side"], "right")

    def test_center_gap_is_isolated(self):
        y = 50.0
        x = 50.0
        pin = self.grid.get_pin_location(x, y)
        self.assertEqual(pin["column"], "gap")
        self.assertEqual(pin["side"], "center")
        
        # Test isolation
        pin_a = self.grid.get_pin_location(20.0, y)
        self.assertFalse(self.grid.same_electrical_node(pin, pin_a))
        self.assertFalse(self.grid.same_electrical_node(pin, pin)) # Gap pins are always isolated

    def test_row_1_to_30_mapping(self):
        x = 20.0  # left side
        # power rail takes 0.08 top and bottom. Main area is 0.08 to 0.92
        y1 = 8.01  # just past top power rail
        pin1 = self.grid.get_pin_location(x, y1)
        self.assertEqual(pin1["row"], 1)

        y30 = 91.99 # just before bottom power rail
        pin30 = self.grid.get_pin_location(x, y30)
        self.assertEqual(pin30["row"], 30)

    def test_same_row_left_side_connected(self):
        y = 50.0
        pin1 = self.grid.get_pin_location(10.0, y)
        pin2 = self.grid.get_pin_location(30.0, y)
        self.assertTrue(self.grid.same_electrical_node(pin1, pin2))

    def test_same_row_right_side_connected(self):
        y = 50.0
        pin1 = self.grid.get_pin_location(70.0, y)
        pin2 = self.grid.get_pin_location(90.0, y)
        self.assertTrue(self.grid.same_electrical_node(pin1, pin2))

    def test_same_row_opposite_sides_not_connected(self):
        y = 50.0
        pin1 = self.grid.get_pin_location(20.0, y)
        pin2 = self.grid.get_pin_location(80.0, y)
        self.assertFalse(self.grid.same_electrical_node(pin1, pin2))

    def test_adjacent_rows_not_connected(self):
        x = 20.0
        # Main area is 84 units tall, 30 rows = 2.8 units per row
        y1 = 15.0 # row ~3
        y2 = 18.0 # row ~4
        pin1 = self.grid.get_pin_location(x, y1)
        pin2 = self.grid.get_pin_location(x, y2)
        self.assertNotEqual(pin1["row"], pin2["row"])
        self.assertFalse(self.grid.same_electrical_node(pin1, pin2))

    def test_top_power_rail_left_half_connected(self):
        y = 4.0 # top rail
        pin1 = self.grid.get_pin_location(10.0, y) # +
        pin2 = self.grid.get_pin_location(20.0, y) # +
        self.assertTrue(pin1["is_power_rail"])
        self.assertEqual(pin1["rail"], "positive")
        self.assertTrue(self.grid.same_electrical_node(pin1, pin2))

    def test_top_power_rail_right_half_connected(self):
        y = 4.0
        pin1 = self.grid.get_pin_location(60.0, y) # -
        pin2 = self.grid.get_pin_location(80.0, y) # -
        self.assertEqual(pin1["rail"], "negative")
        self.assertTrue(self.grid.same_electrical_node(pin1, pin2))

    def test_bottom_power_rail(self):
        y = 96.0 # bottom rail
        pin1 = self.grid.get_pin_location(10.0, y)
        self.assertTrue(pin1["is_power_rail"])
        self.assertEqual(pin1["side"], "bottom_rail")

    def test_power_rail_isolated_from_main(self):
        y_rail = 4.0
        y_main = 50.0
        pin_rail = self.grid.get_pin_location(10.0, y_rail)
        pin_main = self.grid.get_pin_location(10.0, y_main)
        self.assertFalse(self.grid.same_electrical_node(pin_rail, pin_main))

    def test_component_same_row_same_side(self):
        # Two pins manually specified
        pin1 = {"row": 10, "column": "a", "side": "left", "is_power_rail": False}
        pin2 = {"row": 10, "column": "e", "side": "left", "is_power_rail": False}
        self.assertTrue(self.grid.same_electrical_node(pin1, pin2))

    def test_component_spanning_gap(self):
        pin1 = {"row": 10, "column": "e", "side": "left", "is_power_rail": False}
        pin2 = {"row": 10, "column": "f", "side": "right", "is_power_rail": False}
        self.assertFalse(self.grid.same_electrical_node(pin1, pin2))

    def test_connected_components_grouping(self):
        pin1 = {"row": 10, "column": "a", "side": "left", "is_power_rail": False}
        pin2 = {"row": 10, "column": "b", "side": "left", "is_power_rail": False}
        pin3 = {"row": 11, "column": "a", "side": "left", "is_power_rail": False}
        groups = self.grid.connected_components([pin1, pin2, pin3])
        self.assertEqual(len(groups), 2)


if __name__ == '__main__':
    unittest.main()
