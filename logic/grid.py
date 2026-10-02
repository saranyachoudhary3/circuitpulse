class BreadboardGrid:
    def __init__(self, bb_box):
        self.x1 = bb_box['x1']
        self.y1 = bb_box['y1']
        self.x2 = bb_box['x2']
        self.y2 = bb_box['y2']
        
        self.width = max(1, self.x2 - self.x1)
        self.height = max(1, self.y2 - self.y1)
        
        self.is_horizontal = self.width > self.height

    def get_pin_location(self, px, py):
        if not (self.x1 <= px <= self.x2 and self.y1 <= py <= self.y2):
            return None
            
        if self.is_horizontal:
            row = int(((px - self.x1) / self.width) * 30) + 1
            side = "top" if py < self.y1 + (self.height / 2) else "bottom"
        else:
            row = int(((py - self.y1) / self.height) * 30) + 1
            side = "left" if px < self.x1 + (self.width / 2) else "right"
            
        row = max(1, min(30, row))
        return {'row': row, 'side': side}

    def get_component_pins(self, comp_box):
        # Infer physical leg insertion points (bottom corners of bounding box)
        left_leg_x = comp_box['x1'] + (comp_box['x2'] - comp_box['x1']) * 0.2
        right_leg_x = comp_box['x1'] + (comp_box['x2'] - comp_box['x1']) * 0.8
        bottom_y = comp_box['y2']
        
        pin1 = self.get_pin_location(left_leg_x, bottom_y)
        pin2 = self.get_pin_location(right_leg_x, bottom_y)
        
        return pin1, pin2
