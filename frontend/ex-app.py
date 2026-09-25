import streamlit as st
import requests
import time
from PIL import Image
import io

# -----------------------------------------------
# CONFIG
# -----------------------------------------------

import warnings
warnings.filterwarnings("ignore")

# import streamlit as st
# st.set_option("client.showErrorDetails", False)
# st.set_option("client.showWarningOnDirectExecution", False)

FASTAPI_URL = "http://localhost:8000"

st.set_page_config(page_title="ANPR Dashboard", layout="wide")


# -----------------------------------------------
# HELPERS
# -----------------------------------------------

def start_detection():
    r = requests.post(f"{FASTAPI_URL}/anpr/start")
    return r.json()

def stop_detection():
    r = requests.post(f"{FASTAPI_URL}/anpr/stop")
    return r.json()

def get_status():
    r = requests.get(f"{FASTAPI_URL}/anpr/status")
    return r.json()

def get_recent(limit=20):
    r = requests.get(f"{FASTAPI_URL}/anpr/plates/recent?limit={limit}")
    return r.json()

def get_all():
    r = requests.get(f"{FASTAPI_URL}/anpr/plates/all")
    return r.json()

def clear_db():
    r = requests.post(f"{FASTAPI_URL}/anpr/plates/clear")
    return r.json()

def get_video_frame():
    """
    Fetch one JPEG frame streamed by FastAPI.
    Returns None if backend is slow or busy.
    """
    try:
        # shorter timeout for faster UI responsiveness
        r = requests.get(f"{FASTAPI_URL}/video/frame", timeout=0.3)

        if r.status_code == 200:
            return Image.open(io.BytesIO(r.content))

    except requests.exceptions.Timeout:
        # Backend too slow → skip this frame
        return None

    except Exception as e:
        print("Video fetch error:", e)
        return None

    return None



# -----------------------------------------------
# UI LAYOUT
# -----------------------------------------------

st.title("🚘 Automatic Number Plate Recognition System")
tabs = st.tabs(["📹 Live Video", "📜 Records"])


# -------------------------------------------------------------
# TAB 1 — LIVE VIDEO STREAM
# -------------------------------------------------------------
with tabs[0]:

    st.subheader("Live Video Feed")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("▶️ Start Detection"):
            resp = start_detection()
            st.success("Started processing")
            print('DONE!!!!!!!!!!!!!!!!!!!!!!')

        if st.button("⏹ Stop Detection"):
            resp = stop_detection()
            st.warning("Detection stopped")

        if st.button("🗑 Clear Records"):
            clear_db()
            st.info("Database cleared")

    with col2:
        st.write("**Status:**")
        status_box = st.empty()

    st.markdown("---")
    st.subheader("Video")

    frame_box = st.empty()

    # Real-time loop
    while True:
        status = get_status()
        status_box.write(status)

        frame = get_video_frame()
        if frame:
            frame_box.image(frame, caption="Live Stream", use_container_width=True)

        time.sleep(0.2)   # Poll FastAPI


# -------------------------------------------------------------
# TAB 2 — DATABASE RECORDS
# -------------------------------------------------------------
with tabs[1]:
    st.subheader("Detected Plates")

    st.autorefresh(interval=2000, key="refresh_plates")  # refresh every 2 seconds

    data = get_all()
    plates = data.get("plates", [])

    if plates:
        st.table(plates)
    else:
        st.info("No plates detected yet.")
