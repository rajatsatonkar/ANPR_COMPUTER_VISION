# ANPR Smart Gate Entry System

A real-time Automatic Number Plate Recognition (ANPR) system for automated gate access control, built as a final-year B.Tech thesis project (LNMIIT). It detects vehicles and license plates in a video stream, reads the plate text with OCR, and checks it against a database of authorized vehicles to log or flag entry in real time.

Tested on a dataset of 1,385 images, with reliable plate identification and OCR accuracy under normal conditions; character ambiguity and distance from the camera were the main sources of error.

## How it works

1. **Detection** — a YOLOv8 model detects vehicles in each video frame, and a separately fine-tuned YOLOv8 model locates the license plate within each vehicle.
2. **Tracking** — [SORT](https://github.com/abewley/sort) (Simple Online and Realtime Tracking) tracks each vehicle across frames so a plate is only processed once per visit, not once per frame.
3. **OCR** — EasyOCR reads the plate text from the cropped plate region.
4. **Authorization** — the read plate is checked against a SQLite database of allowed/blocked vehicles; entries are logged with a duplicate-suppression window so the same vehicle isn't re-logged repeatedly.
5. **Serving** — a FastAPI backend exposes the detection stream and plate/vehicle data over a REST API; a Streamlit frontend gives a live operator view (start/stop detection, recent plates, authorize/block a vehicle).

## Architecture

```
backend/            FastAPI app
  app.py             app factory, CORS, router registration
  routers/anpr.py     REST endpoints: start/stop detection, recent + all plates, authorize/block, vehicle list
  video_streamer.py   background video processing loop (detection -> tracking -> OCR -> DB)
  detector/           YOLOv8 vehicle + plate models, SORT tracker, OCR/plate-reading utilities
  database.py          SQLite persistence (plates, vehicle authorization status)
frontend/            Streamlit operator UI, talks to the backend over HTTP
```

## Running it

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set the path to your input video (defaults to the bundled demo clip):
```
ANPR_VIDEO_PATH="video3.MOV"
```

Start the backend:
```bash
cd backend
uvicorn app:app --reload
```

Start the frontend, in a separate terminal:
```bash
cd frontend
streamlit run app.py
```

The Streamlit app talks to the FastAPI backend at `http://localhost:8000`.

## Tech stack

Python, YOLOv8 (Ultralytics), EasyOCR, SORT, OpenCV, FastAPI, SQLite, Streamlit

## Credits

Built on the vehicle/plate detection approach from the [Computer Vision Engineer ANPR tutorial](https://github.com/computervisioneng) (YOLOv8 + EasyOCR) and the [abewley/sort](https://github.com/abewley/sort) tracker, extended into a full gate-entry system with a FastAPI backend, SQLite-backed authorization, and a Streamlit operator UI.

## Author

Rajat Satonkar — rajatsatonkar@gmail.com
