"""Site-scoped exception actions shared by the operational frontend."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from schemas.session_exception import PlateCorrectionRequest, SessionExceptionRequest
from services.auth_service import get_current_user
from services.session_exception_service import SessionExceptionService

router = APIRouter()


@router.get("/sites/{site_id}/sessions/{session_id}/ticket")
def session_ticket(site_id: int, session_id: str, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    from expansion.site_service import scoped_session
    from services.ticket_service import get_ticket
    scoped_session(db, actor, site_id, session_id)
    return get_ticket(db, session_id)


@router.get("/sites/{site_id}/sessions/{session_id}/exceptions")
def exception_detail(site_id: int, session_id: str, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return SessionExceptionService(db).detail(actor, site_id, session_id)


@router.post("/sites/{site_id}/sessions/{session_id}/cancel")
def cancel_session(site_id: int, session_id: str, body: SessionExceptionRequest,
                   db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return SessionExceptionService(db).apply(actor, site_id, session_id, body, "cancelled")


@router.post("/sites/{site_id}/sessions/{session_id}/lost-ticket")
def lost_ticket(site_id: int, session_id: str, body: SessionExceptionRequest,
                db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return SessionExceptionService(db).apply(actor, site_id, session_id, body, "lost_ticket")


@router.post("/sites/{site_id}/sessions/{session_id}/correct-plate")
def correct_plate(site_id: int, session_id: str, body: PlateCorrectionRequest,
                  db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return SessionExceptionService(db).apply(actor, site_id, session_id, body, "plate_corrected")
