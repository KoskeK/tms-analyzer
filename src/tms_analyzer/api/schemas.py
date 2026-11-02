from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ReportResponse(BaseModel):
    id: int
    player_count: int
    online: bool
    server_id: int
    time: datetime

    model_config = ConfigDict(from_attributes=True)


class ServerResponse(BaseModel):
    id: int
    ip: str
    tags: str
    url: str
    version: str
    enabled: bool
    addedTime: datetime

    model_config = ConfigDict(from_attributes=True)


class ServerDetail(ServerResponse):
    reports: list[ReportResponse]