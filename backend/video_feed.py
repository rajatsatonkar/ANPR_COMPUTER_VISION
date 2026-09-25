from fastapi import APIRouter, Response
import cv2
from backend.video_streamer import get_global_streamer

router = APIRouter(prefix="/video", tags=["Video Feed"])


@router.get("/frame")
def get_frame():
    """
    Returns the latest processed frame from VideoStreamer as a JPEG image.
    This is polled by Streamlit every ~200ms.
    """

    streamer = get_global_streamer()

    # If no frame available yet:
    if streamer.last_frame is None:
        # Return blank black frame
        blank = _make_blank_frame()
        _, jpeg = cv2.imencode(".jpg", blank)
        return Response(content=jpeg.tobytes(), media_type="image/jpeg")

    frame = streamer.last_frame
    # self.last_frame = frame.copy()

    # Encode to JPEG
    ok, jpeg = cv2.imencode(".jpg", frame)
    if not ok:
        return Response(status_code=500, content=b"Failed to encode frame")

    return Response(content=jpeg.tobytes(), media_type="image/jpeg")


def _make_blank_frame():
    """Returns a simple black frame for early stages when no frame exists."""
    import numpy as np
    return np.zeros((480, 640, 3), dtype=np.uint8)
