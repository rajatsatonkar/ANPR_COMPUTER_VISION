import threading
import time
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Routers will be provided as separate files; main includes them.
# Ensure the routers package (backend.routers.*) is present in the next prompts.
try:
    from backend.routers import anpr as anpr_router
    from backend.routers import vehicles as vehicles_router
    from backend.routers import logs as logs_router
    from backend.routers import dashboard as dashboard_router
except Exception:
    # If routers are not yet present, we will include them later.
    anpr_router = None
    vehicles_router = None
    logs_router = None
    dashboard_router = None

# Detector and DB modules will be provided; these imports assume the
# detector package is at project_root/detector and backend database at backend/database.py
try:
    from backend.plate_stream import NumberPlateStream
except Exception:
    NumberPlateStream = None

try:
    from backend import database
except Exception:
    database = None

from backend import config

app = FastAPI(title="ANPR Backend", version="1.0")

# Allow CORS from local Streamlit (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.BACKEND_CORS_ORIGINS if hasattr(config, "BACKEND_CORS_ORIGINS") else ["http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers if available (files provided in later prompts)
if anpr_router:
    app.include_router(anpr_router.router, prefix="/anpr", tags=["anpr"])
if vehicles_router:
    app.include_router(vehicles_router.router, prefix="/vehicles", tags=["vehicles"])
if logs_router:
    app.include_router(logs_router.router, prefix="/logs", tags=["logs"])
if dashboard_router:
    app.include_router(dashboard_router.router, prefix="/dashboard", tags=["dashboard"])


# Background detector thread state
_detector_thread: Optional[threading.Thread] = None
_detector_stop_flag = threading.Event()


def detector_loop(video_path: str, suppress_minutes: int = 10, sleep_interval: float = 0.01):
    """
    Background loop that continuously reads frames from the NumberPlateStream
    and writes unique plates into the database.

    - video_path: path to the local video to process (config.VIDEO_PATH)
    - suppress_minutes: duplicate suppression window (minutes)
    - sleep_interval: small sleep between polls to avoid CPU spin
    """
    if NumberPlateStream is None:
        app.logger = getattr(app, "logger", None)
        print("Detector not available (NumberPlateStream import failed).")
        return

    # Initialize stream
    try:
        stream = NumberPlateStream(video_path, suppress_minutes=suppress_minutes)
    except Exception as e:
        print("Failed to initialize NumberPlateStream:", e)
        return

    print("Detector loop started on video:", video_path)

    # Local memory dedup (additional safety). database should also enforce unique constraint.
    last_seen_local = {}  # plate -> timestamp

    try:
        while not _detector_stop_flag.is_set():
            plate = stream.get_number_plate()
            if plate:
                ts = time.time()
                # Enforce local suppression (defensive)
                last_ts = last_seen_local.get(plate)
                if last_ts is None or (ts - last_ts) > (suppress_minutes * 60):
                    last_seen_local[plate] = ts

                    # Write to DB (if database module present)
                    if database is not None:
                        try:
                            # database.add_plate should be implemented to insert if not present
                            database.add_plate(plate_text=plate, timestamp=ts)
                        except Exception as ex:
                            print("Failed to write plate to DB:", ex)
                    else:
                        # Temporary fallback: print
                        print(f"[DETECTOR] {time.ctime(ts)} - {plate}")

            if stream.is_finished():
                # For offline video we may stop automatically when finished
                print("Video finished. Detector loop ending.")
                break

            time.sleep(sleep_interval)
    finally:
        try:
            stream.release()
        except Exception:
            pass
        print("Detector loop stopped.")


@app.on_event("startup")
def startup_event():
    """
    Start the detector background thread at app startup.
    """
    global _detector_thread, _detector_stop_flag

    # Ensure DB is initialized (database.init_db should exist)
    if database is not None and hasattr(database, "init_db"):
        try:
            database.init_db()
        except Exception as e:
            print("Warning: database.init_db() failed:", e)

    # Start detector thread only if NumberPlateStream is available
    if NumberPlateStream is not None and _detector_thread is None:
        video_path = getattr(config, "VIDEO_PATH", "video/sample.mp4")
        suppress_minutes = getattr(config, "SUPPRESS_MINUTES", 10)
        _detector_stop_flag.clear()
        _detector_thread = threading.Thread(target=detector_loop, args=(video_path, suppress_minutes), daemon=True)
        _detector_thread.start()
        print("Detector background thread started.")


@app.on_event("shutdown")
def shutdown_event():
    """
    Signal the background detector to stop and wait shortly.
    """
    global _detector_stop_flag, _detector_thread
    _detector_stop_flag.set()
    if _detector_thread is not None:
        _detector_thread.join(timeout=2.0)
    print("API shutdown complete.")


@app.get("/", tags=["root"])
def read_root():
    return {"status": "ok", "message": "ANPR backend running"}


# Basic endpoint to fetch current plates from DB (paginated)
@app.get("/plates")
def get_plates(limit: int = 100, offset: int = 0):
    """
    Return plates from database. Expects backend.database.list_plates(limit, offset).
    """
    if database is None:
        return {"error": "database module not available", "plates": []}
    try:
        plates = database.list_plates(limit=limit, offset=offset)
        return {"plates": plates}
    except Exception as e:
        return {"error": str(e), "plates": []}
