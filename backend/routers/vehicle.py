from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List

from database import get_db
from schemas import vehicle as vehicle_schema
from crud import vehicle as crud_vehicle
from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.parking_session import ParkingSession
from models.vehicle_type import VehicleType
# Nếu cần validate khóa ngoại chặt chẽ, bạn có thể import thêm crud_customer và crud_vehicle_type

router = APIRouter()


def validate_vehicle_relations(db: Session, vehicle_type_id: int | None, customer_id: int | None) -> None:
    if vehicle_type_id is not None and not db.get(VehicleType, vehicle_type_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loại xe không tồn tại")
    if customer_id is not None and not db.get(Customer, customer_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khách hàng không tồn tại")


def validate_vehicle_type_change(
    db: Session,
    vehicle_id: int,
    current_vehicle_type_id: int,
    requested_vehicle_type_id: int | None,
) -> None:
    """Giữ nguyên loại xe sau khi phương tiện đã phát sinh nghiệp vụ.

    Phiên active dùng loại xe hiện tại để tính phí khi check-out; phiên đã
    hoàn tất cũng join qua Vehicle để lập báo cáo. Cho phép đổi loại sau
    khi đã có phiên sẽ làm sai cả phí lẫn lịch sử.
    """
    if (
        requested_vehicle_type_id is None
        or requested_vehicle_type_id == current_vehicle_type_id
    ):
        return

    has_session = (
        db.query(ParkingSession.id)
        .filter(ParkingSession.vehicle_id == vehicle_id)
        .first()
    )
    has_monthly_pass = (
        db.query(MonthlyPass.id)
        .filter(MonthlyPass.vehicle_id == vehicle_id)
        .first()
    )
    if has_session or has_monthly_pass:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Không thể đổi loại xe vì phương tiện đã có phiên gửi xe "
                "hoặc vé tháng."
            ),
        )


def validate_license_plate_change(
    db: Session,
    vehicle_id: int,
    current_license_plate: str,
    requested_license_plate: str | None,
) -> None:
    if (
        requested_license_plate is None
        or requested_license_plate == current_license_plate
    ):
        return
    if db.query(ParkingSession.id).filter(
        ParkingSession.vehicle_id == vehicle_id
    ).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Không thể đổi biển số vì phương tiện đã có lịch sử gửi xe."
            ),
        )

@router.get("", response_model=List[vehicle_schema.VehicleResponse])
def read_vehicles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Lấy danh sách phương tiện"""
    return crud_vehicle.get_vehicles(db, skip=skip, limit=limit)

@router.get("/{id}", response_model=vehicle_schema.VehicleResponse)
def read_vehicle(id: int, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết một phương tiện"""
    db_vehicle = crud_vehicle.get_vehicle(db, vehicle_id=id)
    if not db_vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return db_vehicle

@router.post("", response_model=vehicle_schema.VehicleResponse, status_code=status.HTTP_201_CREATED)
def create_vehicle(vehicle_in: vehicle_schema.VehicleCreate, db: Session = Depends(get_db)):
    """Đăng ký phương tiện mới"""
    # Kiểm tra biển số xe đã tồn tại chưa
    existing_vehicle = crud_vehicle.get_vehicle_by_license_plate(db, license_plate=vehicle_in.license_plate)
    if existing_vehicle:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Biển số xe đã tồn tại")
    validate_vehicle_relations(db, vehicle_in.vehicle_type_id, vehicle_in.customer_id)

    try:
        return crud_vehicle.create_vehicle(db=db, vehicle_in=vehicle_in)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Không thể tạo phương tiện với dữ liệu này")

@router.put("/{id}", response_model=vehicle_schema.VehicleResponse)
def update_vehicle(id: int, vehicle_in: vehicle_schema.VehicleUpdate, db: Session = Depends(get_db)):
    """Cập nhật thông tin phương tiện"""
    db_vehicle = crud_vehicle.get_vehicle(db, vehicle_id=id)
    if not db_vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    
    # Kiểm tra nếu đổi biển số thì biển mới có bị trùng với xe khác không
    if vehicle_in.license_plate and vehicle_in.license_plate != db_vehicle.license_plate:
        existing_vehicle = crud_vehicle.get_vehicle_by_license_plate(db, license_plate=vehicle_in.license_plate)
        if existing_vehicle:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Biển số xe đã được sử dụng")

    validate_vehicle_relations(db, vehicle_in.vehicle_type_id, vehicle_in.customer_id)
    validate_vehicle_type_change(
        db,
        vehicle_id=db_vehicle.id,
        current_vehicle_type_id=db_vehicle.vehicle_type_id,
        requested_vehicle_type_id=vehicle_in.vehicle_type_id,
    )
    validate_license_plate_change(
        db,
        vehicle_id=db_vehicle.id,
        current_license_plate=db_vehicle.license_plate,
        requested_license_plate=vehicle_in.license_plate,
    )
    try:
        return crud_vehicle.update_vehicle(db=db, db_vehicle=db_vehicle, vehicle_in=vehicle_in)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Không thể cập nhật phương tiện với dữ liệu này")

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(id: int, db: Session = Depends(get_db)):
    """Xóa một phương tiện"""
    db_vehicle = crud_vehicle.get_vehicle(db, vehicle_id=id)
    if not db_vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    is_in_use = (
        db.query(ParkingSession.id).filter(ParkingSession.vehicle_id == id).first()
        or db.query(MonthlyPass.id).filter(MonthlyPass.vehicle_id == id).first()
    )
    if is_in_use:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phương tiện đã có lịch sử gửi xe hoặc vé tháng nên không thể xóa")

    try:
        crud_vehicle.delete_vehicle(db=db, db_vehicle=db_vehicle)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phương tiện đang được sử dụng và không thể xóa")
    return None
