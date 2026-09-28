"""Canonical FastAPI application entry point owned by Module E."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import case_router, photo_router


DEVELOPMENT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=DEVELOPMENT_CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)
app.include_router(photo_router)
app.include_router(case_router)

