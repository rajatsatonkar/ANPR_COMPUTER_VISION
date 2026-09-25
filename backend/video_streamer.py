import threading
import time
from collections import deque
from typing import List, Dict, Optional

from backend import config
from backend import database

# Import the NumberPlateStream you saved at backend/plate_stream.py
try:
    from backend.plate_stream import NumberPlateStream
except Exception:
    print('plate_stream import failed in video_streamer.py')
    NumberPlateStream = None


class VideoStreamer:
    """
    Background video streamer that polls NumberPlateStream for plates,
    inserts unique plates into DB, and keeps the latest frame for /video/frame.
    """

    def __init__(self, video_path: Optional[str] = None, suppress_minutes: Optional[int] = None, buffer_size: int = 200):
        self.video_path = video_path or getattr(config, "VIDEO_PATH", "video3.MOV")
        self.suppress_minutes = suppress_minutes if suppress_minutes is not None else getattr(config, "SUPPRESS_MINUTES", 10)
        self.buffer_size = buffer_size

        # Threading / lifecycle
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

        # Recent buffer (most recent first)
        self._recent = deque(maxlen=self.buffer_size)
        self._lock = threading.Lock()

        # Local deduplication: plate -> last seen timestamp
        self._last_seen = {}

        # Last frame (numpy image) to serve via /video/frame
        self.last_frame = None

        # Internal NumberPlateStream instance
        self._stream = None

    def start(self):
        """Start the background streamer (idempotent)."""
        if self._running:
            return
        if NumberPlateStream is None:
            raise RuntimeError("NumberPlateStream not available (backend.plate_stream missing or failed to import).")

        # Reset stop flag and start thread
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        # Wait shortly for thread to set running flag (or error)
        t0 = time.time()
        timeout = 1.0  # seconds
        while not self._running and (time.time() - t0) < timeout:
            time.sleep(0.01)
        if not self._running:
            raise RuntimeError("VideoStreamer failed to start. Check logs for errors.")

    def stop(self, join_timeout: float = 2.0):
        """Signal stop and join thread."""
        if not self._running:
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=join_timeout)
        # release the stream
        try:
            if self._stream:
                self._stream.release()
        except Exception:
            pass
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def get_recent(self, limit: int = 50) -> List[Dict]:
        with self._lock:
            items = list(self._recent)[:limit]
        return [{"plate": it["plate"], "ts": it["ts"], "ts_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(it["ts"]))} for it in items]

    def clear_recent(self):
        with self._lock:
            self._recent.clear()
            self._last_seen.clear()


    def remove_recent_plate(self, plate: str):
        """Remove any entries for `plate` from the in-memory recent buffer and last-seen map."""
        with self._lock:
            items = [it for it in list(self._recent) if it.get("plate") != plate]
            self._recent = deque(items, maxlen=self.buffer_size)
            if plate in self._last_seen:
                del self._last_seen[plate]


    def add_recent_plate(self, plate: str, ts: Optional[float] = None):
        """Add a plate entry to the recent buffer (used when user authorizes manually)."""
        ts = ts or time.time()
        with self._lock:
            # update dedup map
            self._last_seen[plate] = ts
            self._recent.appendleft({"plate": plate, "ts": ts})

    def _normalize_get_number_plate_return(self, result):
        """
        Accepts whatever NumberPlateStream.get_number_plate returned and
        normalizes to (plate_or_None, frame_or_None).
        Handles:
          - None
          - plate_str
          - (plate, frame)
          - (plate, None)
          - (None, frame)
        """
        if result is None:
            return None, None
        if isinstance(result, tuple) or isinstance(result, list):
            # Expect len>=2 or len==1
            if len(result) >= 2:
                return result[0], result[1]
            if len(result) == 1:
                return result[0], None
        # Scalar (plate text)
        return result, None

    def _run_loop(self):
        """
        Main background loop that polls the NumberPlateStream and processes results.
        """
        # Instantiate the NumberPlateStream
        try:
            self._stream = NumberPlateStream(self.video_path, suppress_minutes=self.suppress_minutes)
        except Exception as e:
            print("VideoStreamer: Failed to initialize NumberPlateStream:", e)
            self._running = False
            return

        self._running = True
        print("VideoStreamer: started on", self.video_path)

        try:
            while not self._stop_event.is_set():
                # Call get_number_plate requesting frame if supported
                try:
                    # Prefer call with a return_frame kwarg if supported
                    try:
                        result = self._stream.get_number_plate(return_frame=True)
                    except TypeError:
                        # fallback (no keyword supported)
                        result = self._stream.get_number_plate(True)
                except Exception as e:
                    # If the stream raised on one frame, continue
                    print("VideoStreamer: get_number_plate error:", e)
                    result = None

                plate, frame = self._normalize_get_number_plate_return(result)

                # Update last_frame if frame available
                if frame is not None:
                    try:
                        # store a copy to avoid later mutation
                        self.last_frame = frame.copy() if hasattr(frame, "copy") else frame
                    except Exception:
                        self.last_frame = frame

                # If a plate was detected, check local dedup and insert to DB
                if plate:
                    now = time.time()
                    last = self._last_seen.get(plate)
                    if last is None or (now - last) > (self.suppress_minutes * 60):
                        # update dedup
                        self._last_seen[plate] = now
                        # Check vehicle authorization status (skip if explicitly blocked)
                        try:
                            v = database.get_vehicle_status(plate)
                            if v and v.get("status") == "blocked":
                                # Skip insertion and recent buffer for blocked vehicles
                                # but still update last_seen to suppress repeated detections
                                continue
                        except Exception:
                            pass

                        # write to DB
                        try:
                            database.insert_plate(plate)
                        except Exception as db_ex:
                            print("VideoStreamer: DB insert failed:", db_ex)
                        # push to recent buffer
                        with self._lock:
                            self._recent.appendleft({"plate": plate, "ts": now})
                        print(f"[VideoStreamer] {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))} - {plate}")

                # Stop if underlying stream finished (offline video)
                try:
                    if hasattr(self._stream, "running") and getattr(self._stream, "running") is False:
                        print("VideoStreamer: underlying stream ended. Stopping.")
                        break
                    if hasattr(self._stream, "is_finished") and callable(self._stream.is_finished):
                        if self._stream.is_finished():
                            print("VideoStreamer: underlying stream is_finished → stopping.")
                            break
                except Exception:
                    pass

                # small sleep
                time.sleep(0.01)

        finally:
            try:
                if self._stream:
                    self._stream.release()
            except Exception:
                pass
            self._running = False
            print("VideoStreamer: stopped.")

# Singleton access
_GLOBAL_STREAMER: Optional[VideoStreamer] = None


def get_global_streamer() -> VideoStreamer:
    global _GLOBAL_STREAMER
    if _GLOBAL_STREAMER is None:
        _GLOBAL_STREAMER = VideoStreamer(video_path=config.VIDEO_PATH, suppress_minutes=config.SUPPRESS_MINUTES)
    return _GLOBAL_STREAMER
