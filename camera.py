import cv2
import threading
import time
import urllib.request
from urllib.parse import urlparse, urlunparse
import numpy as np


class CameraSourceError(ValueError):
    pass


def normalize_camera_source(source):
    """Accept USB indexes, explicit stream URLs, or an IP Webcam host:port.

    Android IP Webcam exposes the MJPEG feed at ``/video``.  A bare host:port
    is normalized to that documented endpoint so operators do not accidentally
    route it through OpenCV as an invalid local device path. Other protocols
    such as RTSP remain untouched for OpenCV's native capture path.
    """
    if isinstance(source, int):
        return source
    if not isinstance(source, str) or not source.strip():
        raise CameraSourceError("Camera source must be a USB index or a non-empty stream address.")
    value = source.strip()
    if value.isdigit():
        return int(value)
    if "://" not in value:
        value = f"http://{value}"
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        if not parsed.hostname:
            raise CameraSourceError("HTTP camera source needs a host name or IP address.")
        path = parsed.path if parsed.path and parsed.path != "/" else "/video"
        return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, parsed.fragment))
    return value

class VideoStreamer:
    def __init__(self, src=0, width=640, height=480):
        self.src = normalize_camera_source(src)
        self.is_http = isinstance(self.src, str) and self.src.startswith(("http://", "https://"))
        self.stream = None
        
        self.actual_width = width
        self.actual_height = height
        self.stopped = False
        self.lock = threading.Lock()
        self.frame = None
        self.ret = False
        self.frame_count = 0
        self.reconnect_count = 0
        self.last_frame_monotonic = None

        if not self.is_http:
            self.stream = cv2.VideoCapture(src)
            self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def start(self):
        t = threading.Thread(target=self.update, args=(), daemon=True)
        t.start()
        return self

    def update(self):
        if not self.is_http:
            while not self.stopped:
                self.ret, frame = self.stream.read()
                if self.ret:
                    frame = cv2.resize(frame, (self.actual_width, self.actual_height))
                    with self.lock:
                        self.frame = frame.copy()
                        self.frame_count += 1
                        self.last_frame_monotonic = time.monotonic()
                else:
                    # Auto-reconnect for USB cameras
                    time.sleep(0.5)
                    try:
                        self.stream.release()
                        self.stream = cv2.VideoCapture(self.src)
                        self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, self.actual_width)
                        self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, self.actual_height)
                        self.reconnect_count += 1
                        print(f"[Camera] USB reconnect attempt #{self.reconnect_count}")
                    except Exception:
                        pass
                    time.sleep(0.5)
            return

        # HIGH-SPEED MJPEG STREAM PARSER FOR IP WEBCAM
        while not self.stopped:
            try:
                stream = urllib.request.urlopen(self.src, timeout=5)
                bytes_data = b''
                self.reconnect_count += 1
                if self.reconnect_count > 1:
                    print(f"[Camera] MJPEG stream reconnected (attempt #{self.reconnect_count})")
                
                while not self.stopped:
                    chunk = stream.read(8192)  # Larger chunk for fewer syscalls
                    if not chunk:
                        break  # Stream ended, reconnect
                    bytes_data += chunk
                    
                    # Process all complete JPEG frames in buffer
                    while True:
                        a = bytes_data.find(b'\xff\xd8')  # JPEG start
                        b = bytes_data.find(b'\xff\xd9')  # JPEG end
                        
                        if a == -1 or b == -1:
                            break
                            
                        if b < a:
                            # We found an end marker before a start marker.
                            # This happens if we joined the stream mid-frame.
                            # Discard everything up to the invalid end marker.
                            bytes_data = bytes_data[b+2:]
                            continue
                        
                        jpg = bytes_data[a:b+2]
                        bytes_data = bytes_data[b+2:]
                        
                        img_arr = np.frombuffer(jpg, dtype=np.uint8)
                        frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
                        if frame is not None:
                            h, w = frame.shape[:2]
                            if w != self.actual_width or h != self.actual_height:
                                # Update actual dimensions from first frame
                                if self.frame_count == 0:
                                    self.actual_width = w
                                    self.actual_height = h
                                    print(f"[Camera] Native resolution: {w}x{h}")
                                frame = cv2.resize(frame, (self.actual_width, self.actual_height))
                            with self.lock:
                                self.frame = frame.copy()
                                self.ret = True
                                self.frame_count += 1
                                self.last_frame_monotonic = time.monotonic()
                    
                    # Prevent buffer from growing unbounded
                    if len(bytes_data) > 500000:
                        # Drop old data, keep last 100KB
                        bytes_data = bytes_data[-100000:]
                        
            except Exception as e:
                print(f"[!] MJPEG Stream Error: {e}")
                self.ret = False
                time.sleep(1.5)  # Reconnect delay

    def read(self, max_age_seconds=None):
        with self.lock:
            if (max_age_seconds is not None and (self.last_frame_monotonic is None
                    or time.monotonic() - self.last_frame_monotonic > max_age_seconds)):
                return None
            if self.frame is not None:
                return self.frame.copy()
            return None

    def health(self, max_age_seconds=1.0):
        """Report freshness, not merely whether a frame was ever captured."""
        with self.lock:
            age = None if self.last_frame_monotonic is None else round(time.monotonic() - self.last_frame_monotonic, 3)
            fresh = age is not None and age <= max_age_seconds
            return {"status": "READY" if fresh else "STALE", "frame_age_seconds": age,
                    "frame_count": self.frame_count, "reconnect_count": self.reconnect_count}

    def stop(self):
        self.stopped = True
        if self.stream:
            self.stream.release()
