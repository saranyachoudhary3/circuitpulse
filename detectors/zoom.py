import cv2

class AutoZoom:
    def __init__(self, alpha=0.1, margin=0.3):
        self.alpha = alpha
        self.margin = margin
        self.current_crop = None # [x1, y1, x2, y2]

    def process(self, frame, detections):
        # 1. Find breadboard
        bb_det = next((d for d in detections if d["class"] == "breadboard"), None)
        
        if not bb_det:
            # If no breadboard, slowly zoom out to full frame
            target = [0, 0, frame.shape[1], frame.shape[0]]
        else:
            # Calculate target crop with margin
            bx1, by1, bx2, by2 = bb_det["bbox"]["x1"], bb_det["bbox"]["y1"], bb_det["bbox"]["x2"], bb_det["bbox"]["y2"]
            bw = bx2 - bx1
            bh = by2 - by1
            
            target_x1 = max(0, int(bx1 - (bw * self.margin)))
            target_y1 = max(0, int(by1 - (bh * self.margin)))
            target_x2 = min(frame.shape[1], int(bx2 + (bw * self.margin)))
            target_y2 = min(frame.shape[0], int(by2 + (bh * self.margin)))
            target = [target_x1, target_y1, target_x2, target_y2]

        # Initialize current crop if empty
        if self.current_crop is None:
            self.current_crop = target

        # Apply Exponential Moving Average (EMA) for cinematic smooth camera movement
        cx1 = int(self.current_crop[0] * (1 - self.alpha) + target[0] * self.alpha)
        cy1 = int(self.current_crop[1] * (1 - self.alpha) + target[1] * self.alpha)
        cx2 = int(self.current_crop[2] * (1 - self.alpha) + target[2] * self.alpha)
        cy2 = int(self.current_crop[3] * (1 - self.alpha) + target[3] * self.alpha)
        
        # Enforce minimum size to prevent crashes on weird zero-crops
        if (cx2 - cx1) < 100 or (cy2 - cy1) < 100:
            cx1, cy1, cx2, cy2 = 0, 0, frame.shape[1], frame.shape[0]

        self.current_crop = [cx1, cy1, cx2, cy2]

        # Perform the actual crop
        cropped_frame = frame[cy1:cy2, cx1:cx2]

        # Translate all detection coordinates to the new cropped space
        translated_detections = []
        for d in detections:
            new_d = d.copy()
            new_bbox = d["bbox"].copy()
            new_bbox["x1"] -= cx1
            new_bbox["x2"] -= cx1
            new_bbox["y1"] -= cy1
            new_bbox["y2"] -= cy1
            new_d["bbox"] = new_bbox
            
            if "endpoints" in new_d:
                new_eps = []
                for ep in new_d["endpoints"]:
                    new_eps.append([ep[0] - cx1, ep[1] - cy1])
                new_d["endpoints"] = new_eps
                
            translated_detections.append(new_d)

        return cropped_frame, translated_detections
