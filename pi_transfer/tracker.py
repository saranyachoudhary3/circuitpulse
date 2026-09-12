class BoxSmoother:
    def __init__(self, alpha=0.65, iou_thresh=0.38, max_missing=2):
        self.alpha = alpha
        self.iou_thresh = iou_thresh
        self.max_missing = max_missing
        self.tracks = {}
        self.next_id = 1

    def _iou(self, b1, b2):
        x1 = max(b1["x1"], b2["x1"])
        y1 = max(b1["y1"], b2["y1"])
        x2 = min(b1["x2"], b2["x2"])
        y2 = min(b1["y2"], b2["y2"])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (b1["x2"] - b1["x1"]) * (b1["y2"] - b1["y1"])
        area2 = (b2["x2"] - b2["x1"]) * (b2["y2"] - b2["y1"])
        union = area1 + area2 - inter
        return inter / union if union > 0 else 0.0

    def update(self, detected_boxes):
        matched_track_ids = set()
        matched_box_indices = set()

        for t_id, track in list(self.tracks.items()):
            best_iou = 0
            best_idx = -1
            for i, box in enumerate(detected_boxes):
                if i in matched_box_indices:
                    continue
                if box["class"] == track["class"]:
                    iou = self._iou(box["bbox"], track["bbox"])
                    if iou > best_iou:
                        best_iou = iou
                        best_idx = i

            if best_iou >= self.iou_thresh and best_idx != -1:
                matched_track_ids.add(t_id)
                matched_box_indices.add(best_idx)
                new_box = detected_boxes[best_idx]
                old_b = track["bbox"]
                cur_b = new_box["bbox"]

                track["bbox"] = {
                    "x1": int(self.alpha * cur_b["x1"] + (1 - self.alpha) * old_b["x1"]),
                    "y1": int(self.alpha * cur_b["y1"] + (1 - self.alpha) * old_b["y1"]),
                    "x2": int(self.alpha * cur_b["x2"] + (1 - self.alpha) * old_b["x2"]),
                    "y2": int(self.alpha * cur_b["y2"] + (1 - self.alpha) * old_b["y2"]),
                }
                track["confidence"] = round(0.7 * new_box["confidence"] + 0.3 * track["confidence"], 3)
                track["missing"] = 0
            else:
                track["missing"] += 1

        for t_id in list(self.tracks.keys()):
            if self.tracks[t_id]["missing"] > self.max_missing:
                del self.tracks[t_id]

        for i, box in enumerate(detected_boxes):
            if i not in matched_box_indices:
                self.tracks[self.next_id] = {
                    "class": box["class"],
                    "confidence": box["confidence"],
                    "bbox": dict(box["bbox"]),
                    "missing": 0,
                }
                self.next_id += 1

        output = []
        for t_id, track in self.tracks.items():
            if track["missing"] == 0:
                output.append({
                    "class": track["class"],
                    "confidence": track["confidence"],
                    "bbox": track["bbox"],
                })
        return output
