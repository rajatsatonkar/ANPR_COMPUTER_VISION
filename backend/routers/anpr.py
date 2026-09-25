from fastapi import APIRouter, HTTPException, Body
from backend.video_streamer import get_global_streamer
from backend.database import (
    get_all_plates,
    clear_database,
    set_vehicle_status,
    get_all_vehicles,
    insert_plate,
    plate_exists,
    delete_plate_by_number,
    get_vehicle_status,
)

router = APIRouter(prefix="/anpr", tags=["ANPR"])


@router.get("/status", name="anpr_status")
def status():
    """
    Returns whether the video streamer is running.
    """
    streamer = get_global_streamer()
    return {
        "running": streamer.is_running(),
        "video_path": streamer.video_path
    }


@router.post("/start", name='anpr_start_detection')
def start_detection():
    """
    Starts the video streamer in the background.
    """
    streamer = get_global_streamer()

    try:
        streamer.start()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "started", "video_path": streamer.video_path}


@router.post("/stop",name='anpr_stop_detection')
def stop_detection():
    """
    Stops the video streamer.
    """
    streamer = get_global_streamer()
    streamer.stop()
    return {"status": "stopped"}


@router.get("/plates/recent",name='anpr_get_recent_plates')
def get_recent_plates(limit: int = 10):
    """
    Returns recent plates detected (last N).
    """
    streamer = get_global_streamer()
    recents = streamer.get_recent(limit=limit)
    return {"plates": recents}


@router.post("/plates/clear_recent", name='anpr_clear_recent')
def clear_recent():
    """
    Clears the recent in-memory detections buffer on the streamer.
    """
    streamer = get_global_streamer()
    streamer.clear_recent()
    return {"status": "recent_cleared"}


@router.get("/plates/all",name='anpr_get_all')
def get_all():
    """
    Returns all plates stored in the DB.
    """
    plates = get_all_plates()
    # merge authorization status per plate
    merged = []
    for p in plates:
        plate_text = p.get("number_plate")
        status_row = get_vehicle_status(plate_text)
        p_out = dict(p)
        p_out["status"] = status_row.get("status") if status_row else "unknown"
        merged.append(p_out)
    return {"plates": merged}


@router.post("/plates/authorize", name='anpr_authorize')
def authorize_plate(payload: dict = Body(...)):
    """
    Authorize or block a vehicle globally.
    Payload: {"plate": "ABC123", "allow": true}
    """
    plate = payload.get("plate")
    allow = payload.get("allow")
    if not plate or allow is None:
        raise HTTPException(status_code=400, detail="payload must include 'plate' and 'allow' boolean")
    status = "allowed" if bool(allow) else "blocked"
    set_vehicle_status(plate, status)

    # Manage plates DB and in-memory recent buffer depending on allow/block
    streamer = get_global_streamer()

    if status == "allowed":
        try:
            if not plate_exists(plate):
                insert_plate(plate)
            # also add to recent buffer so UI can show it immediately
            try:
                streamer.add_recent_plate(plate)
            except Exception:
                pass
        except Exception:
            # don't fail the request on DB insert error
            pass

    if status == "blocked":
        try:
            delete_plate_by_number(plate)
        except Exception:
            pass
        # remove from in-memory recent buffer so it's not shown immediately
        try:
            streamer.remove_recent_plate(plate)
        except Exception:
            pass

    return {"plate": plate, "status": status}


@router.get("/vehicles", name='anpr_get_vehicles')
def list_vehicles():
    """Returns all vehicles with their authorization status."""
    return {"vehicles": get_all_vehicles()}


@router.post("/plates/clear",name='anpr_clear')
def clear():
    """
    Clears the plate database.
    Useful for debugging.
    """
    clear_database()
    return {"status": "cleared"}
