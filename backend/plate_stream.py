import cv2
import time
import numpy as np
from ultralytics import YOLO
from backend.detector.util import read_license_plate, get_car


class NumberPlateStream:
    """
    Reads the video frame-by-frame, detects plates, removes duplicates,
    and optionally returns frames.
    """

    def __init__(self, video_path, suppress_minutes=10):
        self.video_path = video_path
        self.cap = cv2.VideoCapture(video_path)

        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open video: {video_path}")

        # Load YOLO models

        self.coco_model = YOLO("yolov8n.pt")#.to("cuda")
        self.plate_model = YOLO("./models/license_plate_detector.pt")#.to("cuda")


        # Vehicle classes: car, bike, bus, truck
        self.vehicles = [2, 3, 5, 7]

        # Prevent duplicates
        self.last_seen = {}
        self.SUPPRESS_TIME = suppress_minutes * 60  # convert to seconds

        self.running = True
        print('NumberPlateStream initialized with video:', video_path)

    def release(self):
        self.running = False
        try:
            self.cap.release()
        except:
            pass

    def get_number_plate(self, return_frame=False):
        """
        Returns:
            (plate_text, frame)
            OR
            (plate_text, None)
        """

        if not self.running:
            return None, None

        ret, frame = self.cap.read()
        if not ret:
            self.running = False
            return None, frame  # frame=None when finished

        # ---------------- VEHICLE DETECTION ----------------
        res = self.coco_model(frame)[0]
        detections = []
        for x1, y1, x2, y2, score, cls in res.boxes.data.tolist():
            if int(cls) in self.vehicles:
                detections.append([x1, y1, x2, y2, score])

        dets = np.asarray(detections) if len(detections) else np.empty((0, 5))

        # ---------------- PLATE DETECTION ----------------
        plates = self.plate_model(frame)[0]

        for plate in plates.boxes.data.tolist():
            x1, y1, x2, y2, score, cls = plate

            car_x1, car_y1, car_x2, car_y2, car_id = get_car(plate, dets)
            if car_id == -1:
                continue

            crop = frame[int(y1):int(y2), int(x1):int(x2)]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 64, 255, cv2.THRESH_BINARY_INV)

            plate_text, confidence = read_license_plate(thresh)
            if not plate_text:
                continue

            # Duplicate filtering
            now = time.time()
            if plate_text in self.last_seen:
                if now - self.last_seen[plate_text] < self.SUPPRESS_TIME:
                    continue

            self.last_seen[plate_text] = now
            return plate_text, frame if return_frame else plate_text, None

        return None, frame if return_frame else None, None
