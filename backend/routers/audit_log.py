from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
from models.audit_log import AuditLog
from schemas.audit_log import AuditLogResponse
from services.auth_service import RoleChecker


router = APIRouter(dependencies=[Depends(RoleChecker("manager"))])


@router.get("", response_model=list[AuditLogResponse])
def read_audit_logs(
    db: Annotated[Session, Depends(get_db)],
    action: Optional[str] = Query(None),
    username: Optional[str] = Query(None, max_length=50),
    success: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action.upper())
    if username:
        query = query.filter(AuditLog.username.ilike(f"%{username.strip()}%"))
    if success is not None:
        query = query.filter(AuditLog.success == success)
    return query.order_by(desc(AuditLog.created_at), desc(AuditLog.id)).offset(skip).limit(limit).all()
