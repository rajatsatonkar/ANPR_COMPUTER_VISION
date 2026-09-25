import os

#
# ---------- VIDEO + DETECTOR SETTINGS ----------
#

# Path to video processed by NumberPlateStream
# (relative or absolute)
VIDEO_PATH = os.getenv("ANPR_VIDEO_PATH", "video3.MOV")

# Duplicate-suppression window (minutes)
SUPPRESS_MINUTES = int(os.getenv("ANPR_SUPPRESS_MINUTES", 10))


#
# ---------- DATABASE SETTINGS ----------
#

# SQLite DB file
DB_PATH = os.getenv("ANPR_DB_PATH", "backend/anpr.db")


#
# ---------- WEB APP SETTINGS ----------
#

# Allow local Streamlit to call FastAPI
BACKEND_CORS_ORIGINS = [
    "http://localhost:8501",
    "http://127.0.0.1:8501",
    "http://localhost",
    "http://127.0.0.1",
]

DEBUG = True
