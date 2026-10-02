import cv2
import numpy as np

class WireTracer:
    @staticmethod
    def get_endpoints(frame, wire_box):
        x1, y1 = int(wire_box['x1']), int(wire_box['y1'])
        x2, y2 = int(wire_box['x2']), int(wire_box['y2'])
        
        # Ensure box is within frame
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None, None
            
        # 1. Convert to HSV
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        
        # 2. Create masks for common wire colors
        # Red
        mask_red1 = cv2.inRange(hsv, np.array([0, 50, 50]), np.array([10, 255, 255]))
        mask_red2 = cv2.inRange(hsv, np.array([170, 50, 50]), np.array([180, 255, 255]))
        mask_red = cv2.bitwise_or(mask_red1, mask_red2)
        
        # Blue
        mask_blue = cv2.inRange(hsv, np.array([100, 50, 50]), np.array([130, 255, 255]))
        
        # Green
        mask_green = cv2.inRange(hsv, np.array([35, 50, 50]), np.array([85, 255, 255]))
        
        # Yellow
        mask_yellow = cv2.inRange(hsv, np.array([20, 50, 50]), np.array([35, 255, 255]))
        
        # Orange
        mask_orange = cv2.inRange(hsv, np.array([10, 50, 50]), np.array([20, 255, 255]))
        
        # Black
        mask_black = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 255, 50]))
        
        # White
        mask_white = cv2.inRange(hsv, np.array([0, 0, 200]), np.array([180, 30, 255]))
        
        # 3. Combine masks
        combined_mask = mask_red | mask_blue | mask_green | mask_yellow | mask_orange | mask_black | mask_white
        
        # 4. Morphological operations
        kernel = np.ones((5, 5), np.uint8)
        closed = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)
        
        skeleton = None
        if hasattr(cv2, 'ximgproc') and hasattr(cv2.ximgproc, 'thinning'):
            skeleton = cv2.ximgproc.thinning(closed)
        else:
            skeleton = np.zeros(closed.shape, np.uint8)
            img = closed.copy()
            element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
            done = False
            while not done:
                eroded = cv2.erode(img, element)
                temp = cv2.dilate(eroded, element)
                temp = cv2.subtract(img, temp)
                skeleton = cv2.bitwise_or(skeleton, temp)
                img = eroded.copy()
                if cv2.countNonZero(img) == 0:
                    done = True
                    
        # 5. Find two points furthest apart
        points = np.column_stack(np.where(skeleton > 0)) # (y, x)
        
        ep1, ep2 = None, None
        success = False
        
        if len(points) >= 2:
            # simple O(N) max dist approximation
            center_y, center_x = closed.shape[0] // 2, closed.shape[1] // 2
            dists_to_center = (points[:, 0] - center_y)**2 + (points[:, 1] - center_x)**2
            p1_idx = np.argmax(dists_to_center)
            p1 = points[p1_idx]
            
            dists_to_p1 = (points[:, 0] - p1[0])**2 + (points[:, 1] - p1[1])**2
            p2_idx = np.argmax(dists_to_p1)
            p2 = points[p2_idx]
            
            ep1 = (int(p1[1]), int(p1[0])) # (x, y)
            ep2 = (int(p2[1]), int(p2[0]))
            
            if dists_to_p1[p2_idx] > 0:
                success = True
                
        # 6. Fallback
        if not success:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 150)
            
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest_contour = max(contours, key=cv2.contourArea)
                
                extLeft = tuple(largest_contour[largest_contour[:, :, 0].argmin()][0])
                extRight = tuple(largest_contour[largest_contour[:, :, 0].argmax()][0])
                extTop = tuple(largest_contour[largest_contour[:, :, 1].argmin()][0])
                extBot = tuple(largest_contour[largest_contour[:, :, 1].argmax()][0])
                
                ext_points = [extLeft, extRight, extTop, extBot]
                max_dist = 0
                cp1, cp2 = ext_points[0], ext_points[1]
                
                for i in range(len(ext_points)):
                    for j in range(i+1, len(ext_points)):
                        d = (ext_points[i][0] - ext_points[j][0])**2 + (ext_points[i][1] - ext_points[j][1])**2
                        if d > max_dist:
                            max_dist = d
                            cp1, cp2 = ext_points[i], ext_points[j]
                
                ep1, ep2 = cp1, cp2

        if ep1 is None or ep2 is None:
            return None, None
            
        # 7. Map crop coordinates back to full frame
        final_ep1 = (ep1[0] + x1, ep1[1] + y1)
        final_ep2 = (ep2[0] + x1, ep2[1] + y1)
        
        return final_ep1, final_ep2
