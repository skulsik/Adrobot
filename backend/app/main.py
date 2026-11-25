from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.database import get_db


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Advertising campaign management system",
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "adrobot-backend",
    }


@app.get("/api/v1/health")
def api_health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))

        return {
            "status": "ok",
            "database": "connected",
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )