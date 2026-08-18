from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from models.ai_report import AiReport 
from schemas import ai_report as ai_report_schema

def get_ai_report(db: Session, report_id: int) -> AiReport | None:
    stmt = select(AiReport).where(AiReport.id == report_id)
    return db.execute(stmt).scalar_one_or_none()

def get_ai_reports(db: Session, skip: int = 0, limit: int = 100):
    # Thường thì báo cáo AI sẽ cần xem cái mới nhất trước, nên ta thêm order_by(desc())
    stmt = select(AiReport).order_by(desc(AiReport.id)).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()

def create_ai_report(db: Session, report_in: ai_report_schema.AiReportCreate) -> AiReport:
    db_report = AiReport(**report_in.model_dump())
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report

def update_ai_report(db: Session, db_report: AiReport, report_in: ai_report_schema.AiReportUpdate) -> AiReport:
    update_data = report_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_report, field, value)
    
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report

def delete_ai_report(db: Session, db_report: AiReport) -> AiReport:
    db.delete(db_report)
    db.commit()
    return db_report