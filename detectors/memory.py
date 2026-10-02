import cv2
import math

class WireMemory:
    def __init__(self, max_missing=5, movement_thresh=20):
        # Maps track_id -> {"endpoints": [(x,y), (x,y)], "missing": int, "bbox": (x1,y1,x2,y2)}
        self.tracks = {}
        self.max_missing = max_missing
        self.movement_thresh = movement_thresh
        self.next_id = 1

    def _center(self, bbox):
        return ((bbox["x1"] + bbox["x2"]) / 2, (bbox["y1"] + bbox["y2"]) / 2)

    def _dist(self, p1, p2):
        return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

    def update(self, detections):
        matched_tracks = set()
        
        for det in detections:
            if det["class"] != "wire":
                continue
                
            det_center = self._center(det["bbox"])
            best_id = -1
            best_dist = float('inf')
            
            for t_id, track in self.tracks.items():
                if t_id in matched_tracks:
                    continue
                d = self._dist(det_center, self._center(track["bbox"]))
                if d < self.movement_thresh and d < best_dist:
                    best_dist = d
                    best_id = t_id
                    
            has_new_eps = "endpoints" in det and det["endpoints"] is not None and len(det["endpoints"]) == 2
            
            if best_id != -1:
                # Matched an existing track
                matched_tracks.add(best_id)
                self.tracks[best_id]["bbox"] = det["bbox"]
                
                if has_new_eps:
                    # Apply EMA to endpoints for buttery smooth wire tracking
                    old_eps = self.tracks[best_id]["endpoints"]
                    new_eps = det["endpoints"]
                    
                    # Match endpoints by distance to avoid crossing wires
                    d1 = self._dist(old_eps[0], new_eps[0]) + self._dist(old_eps[1], new_eps[1])
                    d2 = self._dist(old_eps[0], new_eps[1]) + self._dist(old_eps[1], new_eps[0])
                    
                    alpha = 0.3 # Smoothness factor
                    
                    if d1 < d2:
                        e0 = [int(old_eps[0][0]*(1-alpha) + new_eps[0][0]*alpha), int(old_eps[0][1]*(1-alpha) + new_eps[0][1]*alpha)]
                        e1 = [int(old_eps[1][0]*(1-alpha) + new_eps[1][0]*alpha), int(old_eps[1][1]*(1-alpha) + new_eps[1][1]*alpha)]
                    else:
                        e0 = [int(old_eps[0][0]*(1-alpha) + new_eps[1][0]*alpha), int(old_eps[0][1]*(1-alpha) + new_eps[1][1]*alpha)]
                        e1 = [int(old_eps[1][0]*(1-alpha) + new_eps[0][0]*alpha), int(old_eps[1][1]*(1-alpha) + new_eps[0][1]*alpha)]
                        
                    self.tracks[best_id]["endpoints"] = [e0, e1]
                    self.tracks[best_id]["missing"] = 0
                    det["endpoints"] = [e0, e1]
                else:
                    # Wire detected but endpoints failed this frame (occlusion/glare)
                    # Use hysterical memory
                    self.tracks[best_id]["missing"] += 1
                    det["endpoints"] = self.tracks[best_id]["endpoints"]
            else:
                # New wire
                if has_new_eps:
                    self.tracks[self.next_id] = {
                        "bbox": det["bbox"],
                        "endpoints": det["endpoints"],
                        "missing": 0
                    }
                    matched_tracks.add(self.next_id)
                    self.next_id += 1

        # Clean up stale tracks
        for t_id in list(self.tracks.keys()):
            if t_id not in matched_tracks:
                self.tracks[t_id]["missing"] += 1
                if self.tracks[t_id]["missing"] > self.max_missing:
                    del self.tracks[t_id]
                    
        return detections
