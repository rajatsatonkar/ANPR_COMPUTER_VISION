import streamlit as st
import requests
import time
from PIL import Image
import io
import threading
import queue

FASTAPI_URL = "http://localhost:8000"


# ---------------------------------------------------------
# API HELPERS
# ---------------------------------------------------------

def start_detection():
    return requests.post(f"{FASTAPI_URL}/anpr/start").json()

def stop_detection():
    return requests.post(f"{FASTAPI_URL}/anpr/stop").json()

def get_status():
    return requests.get(f"{FASTAPI_URL}/anpr/status").json()

def clear_db():
    return requests.post(f"{FASTAPI_URL}/anpr/plates/clear").json()


def clear_recent():
    return requests.post(f"{FASTAPI_URL}/anpr/plates/clear_recent").json()


def authorize_plate(plate: str, allow: bool):
    return requests.post(f"{FASTAPI_URL}/anpr/plates/authorize", json={"plate": plate, "allow": allow}).json()

def get_all_records():
    return requests.get(f"{FASTAPI_URL}/anpr/plates/all").json()

def get_video_frame():
    """
    Safely fetch one frame (JPEG) from backend.
    No auto-looping. Only called when user clicks refresh.
    """
    try:
        r = requests.get(f"{FASTAPI_URL}/video/frame", timeout=1)
        if r.status_code == 200:
            return Image.open(io.BytesIO(r.content))
    except:
        return None
    return None


# ---------------------------------------------------------
# Live listener (polling) — runs in background thread
# ---------------------------------------------------------

def _ensure_listener_state():
    if "event_q" not in st.session_state:
        st.session_state.event_q = queue.Queue()
    if "listener_thread" not in st.session_state:
        st.session_state.listener_thread = None
    if "listener_stop_event" not in st.session_state:
        st.session_state.listener_stop_event = None
    if "events_display" not in st.session_state:
        st.session_state.events_display = []


def start_live_listener(poll_interval: float = 0.6):
    """Start a background thread that polls status and recent plates.
    It pushes new plate detections and a finished event into `st.session_state.event_q`.
    """
    _ensure_listener_state()

    # If already running, do nothing
    thr = st.session_state.listener_thread
    if thr and thr.is_alive():
        return

    stop_event = threading.Event()

    def poller(stop_evt: threading.Event, q: queue.Queue):
        last_seen = set()
        was_running = False
        while not stop_evt.is_set():
            try:
                # status
                status = get_status()
                running = bool(status.get("running", False))

                # recent plates
                try:
                    r = requests.get(f"{FASTAPI_URL}/anpr/plates/recent?limit=20", timeout=2)
                    if r.status_code == 200:
                        rec = r.json().get("plates", [])
                        for item in rec:
                            plate = item.get("plate")
                            if plate and plate not in last_seen:
                                last_seen.add(plate)
                                q.put({"type": "plate", "plate": plate, "ts": item.get("ts")})
                except Exception:
                    pass

                # detect transition from running -> not running (video finished)
                if was_running and not running:
                    q.put({"type": "finished"})

                was_running = running
            except Exception:
                # swallow; keep polling
                pass
            time.sleep(poll_interval)

    st.session_state.event_q = queue.Queue()
    st.session_state.listener_stop_event = stop_event
    t = threading.Thread(target=poller, args=(stop_event, st.session_state.event_q), daemon=True)
    st.session_state.listener_thread = t
    t.start()


def stop_live_listener():
    _ensure_listener_state()
    ev = st.session_state.get("listener_stop_event")
    if ev:
        ev.set()
    thr = st.session_state.get("listener_thread")
    if thr and thr.is_alive():
        thr.join(timeout=1.0)
    st.session_state.listener_thread = None
    st.session_state.listener_stop_event = None


# ---------------------------------------------------------
# STREAMLIT UI
# ---------------------------------------------------------

st.set_page_config(page_title="ANPR Dashboard", layout="wide")
st.title("🚘 Automatic Number Plate Recognition System")

tab_live, tab_records = st.tabs(["📹 Video Feed", "📜 Records"])


# =========================================================
# TAB 1 — VIDEO FEED
# =========================================================
with tab_live:

    st.subheader("Video Controls")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("▶️ Start Detection", use_container_width=True):
            start_detection()
            st.success("Detection started.")

        if st.button("⏹ Stop Detection", use_container_width=True):
            stop_detection()
            st.warning("Detection stopped.")

        if st.button("🗑 Clear Records", use_container_width=True):
            clear_db()
            st.info("Database cleared.")

        if st.button("🧹 Clear Recent Detections", use_container_width=True):
            clear_recent()
            st.info("Recent detection buffer cleared.")

    with col2:
        status = get_status()
        st.write("### Status:")
        st.json(status)

    st.markdown("---")

    st.subheader("Video Preview")

    # Placeholder for last shown frame
    frame_box = st.empty()

    if st.button("🔄 Refresh Video Frame", use_container_width=True):
        frame = get_video_frame()
        if frame:
            frame_box.image(frame, caption="Latest Frame", use_container_width=True)
        else:
            st.error("No frame available. (Video may have ended.)")

    # Live mode controls and event area
    _ensure_listener_state()
    live = st.checkbox("🔔 Live Mode (show detections as they happen)", value=False)
    if live:
        start_live_listener()
    else:
        stop_live_listener()

    # Drain event queue and show notifications
    events_placeholder = st.empty()
    # initialize storage
    if "events_display" not in st.session_state:
        st.session_state.events_display = []

    # Pull all available events from the queue
    try:
        q = st.session_state.get("event_q")
        if q:
            while True:
                ev = q.get_nowait()
                if ev.get("type") == "plate":
                    plate = ev.get("plate")
                    ts = ev.get("ts")
                    st.session_state.events_display.insert(0, f"Detected: {plate}")
                    st.success(f"Detected: {plate}")
                elif ev.get("type") == "finished":
                    st.session_state.events_display.insert(0, "Video finished")
                    st.info("Video finished")
    except Exception:
        pass

    # Show recent event list
    if st.session_state.events_display:
        events_placeholder.markdown("**Recent events:**")
        for line in st.session_state.events_display[:20]:
            events_placeholder.write(line)



# =========================================================
# TAB 2 — RECORDS
# =========================================================
with tab_records:

    st.subheader("Detected License Plates")

    # session-state store for previous record length
    if "prev_count" not in st.session_state:
        st.session_state.prev_count = 0

    if st.button("🔄 Refresh Records", use_container_width=True):
        data = get_all_records()
        plates = data.get("plates", [])

        new_count = len(plates)
        diff = new_count - st.session_state.prev_count

        if diff > 0:
            st.success(f"✅ {diff} new plate(s) detected since last refresh!")
        elif new_count == 0:
            st.info("No plates detected yet.")
        else:
            st.info("No new plates.")

        st.session_state.prev_count = new_count

        # show interactive list with allow/block buttons
        if plates:
            for i, p in enumerate(plates):
                plate_text = p.get("number_plate") or p.get("plate") or p.get("number_plate")
                ts = p.get("timestamp") or p.get("ts_iso") or p.get("ts")
                c1, c2, c3 = st.columns([2, 1, 1])
                with c1:
                    st.write(f"**{plate_text}** — {ts}")
                with c2:
                    key_allow = f"allow_{i}_{plate_text}"
                    if st.button("Allow", key=key_allow):
                        try:
                            authorize_plate(plate_text, True)
                            st.success(f"{plate_text} allowed.")
                        except Exception:
                            st.error("Failed to authorize")
                with c3:
                    key_block = f"block_{i}_{plate_text}"
                    if st.button("Block", key=key_block):
                        try:
                            authorize_plate(plate_text, False)
                            st.warning(f"{plate_text} blocked.")
                        except Exception:
                            st.error("Failed to block")

    else:
        st.info("Click **Refresh Records** to load records.")
