from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from tms_analyzer.shared.database import init_db, get_db
from tms_analyzer.shared.models import Server
from tms_analyzer.api.schemas import ServerResponse, ReportResponse


app = FastAPI(
    title="TMS Analyzer API",
    description="Read-only API for server information",
    version="1.0.0",
)

# Initialize database
init_db()


@app.get("/")
def root():
    return {"message": "TMS Analyzer API"}


@app.get("/servers/newest", response_model=ServerResponse)
def get_newest_server(db: Session = Depends(get_db)):
    statement = (
        select(Server)
        .order_by(Server.addedTime.desc(), Server.id.desc())
        .limit(1)
    )

    server = db.scalar(statement)

    if server is None:
        raise HTTPException(
            status_code=404,
            detail="No servers found",
        )

    return server