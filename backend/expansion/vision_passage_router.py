"""Camera automation requires an authenticated operator, never an edge token."""
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from expansion.site_scope import require_site_access
from expansion.vision_passage_models import CameraAutomationPolicy, VisionPassageEvent
from expansion.vision_passage_schemas import AutomationPolicyUpdate
from expansion import vision_passage_service as service
from models.user import User
from services.auth_service import RoleChecker, get_current_user

router = APIRouter(prefix="/api/v2", tags=["Vận hành camera"], dependencies=[Depends(RoleChecker("staff"))])


@router.get("/cameras/{camera_id}/automation")
def policy(camera_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    camera = service.camera_for(db, actor, camera_id)
    return service.policy_view(camera, db.get(CameraAutomationPolicy, camera_id))


@router.put("/cameras/{camera_id}/automation")
def configure(camera_id: int, body: AutomationPolicyUpdate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return service.update_policy(db, actor, camera_id, body)


@router.post("/vision/observations/{observation_id}/process")
def process(observation_id: str, response: Response, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    return service.process_observation(db, actor, observation_id)


@router.get("/vision/passages")
def events(response: Response, site_id: int = Query(gt=0), camera_id: int | None = Query(None, gt=0),
           limit: int = Query(25, ge=1, le=100), db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_site_access(db, actor, site_id)
    query = select(VisionPassageEvent).where(VisionPassageEvent.site_id == site_id)
    if camera_id is not None:
        query = query.where(VisionPassageEvent.camera_id == camera_id)
    response.headers["Cache-Control"] = "no-store"
    return [service.event_view(row) for row in db.scalars(query.order_by(VisionPassageEvent.processed_at.desc(), VisionPassageEvent.id).limit(limit))]
