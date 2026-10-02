import os
import cv2
import time
from datetime import datetime

class SnapshotManager:
    def __init__(self, save_dir="snapshots"):
        self.save_dir = save_dir
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)
        self.last_snap_time = 0

    def check_and_snap(self, report, frame):
        # Only take a snapshot if the circuit is perfectly completed and we haven't snapped in the last 10 seconds
        if report.get("status") == "PASS" and not report.get("current_step") and report.get("circuit_name") != "scanning":
            now = time.time()
            if now - self.last_snap_time > 10:
                self.last_snap_time = now
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                c_name = report.get("circuit_name", "circuit").replace(" ", "_").lower()
                filepath = os.path.join(self.save_dir, f"{c_name}_complete_{timestamp}.jpg")
                cv2.imwrite(filepath, frame)
                print(f" Snapshot saved to {filepath}")
                return filepath
        return None
