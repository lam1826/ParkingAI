from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int]
    username: str
    action: str
    resource: str
    resource_id: Optional[str]
    request_id: Optional[str] = None
    site_id: Optional[int] = None
    duration_ms: Optional[int] = None
    method: str
    path: str
    status_code: int
    success: bool
    ip_address: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
