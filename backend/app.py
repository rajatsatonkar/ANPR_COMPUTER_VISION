from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.routers.anpr import router as anpr_router
from backend.video_feed import router as video_router


def create_app():
    app = FastAPI(
        title="ANPR Backend",
        description="FastAPI backend for Number Plate Recognition system",
        version="1.0",
    )

    # ----------------------------------------------------------
    # CORS (Streamlit frontend needs this)
    # ----------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # Allow Streamlit frontend
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ----------------------------------------------------------
    # Initialize SQLite database
    # ----------------------------------------------------------
    init_db()

    # ----------------------------------------------------------
    # API Routers
    # ----------------------------------------------------------
    app.include_router(anpr_router)
    app.include_router(video_router)


    return app


app = create_app()
