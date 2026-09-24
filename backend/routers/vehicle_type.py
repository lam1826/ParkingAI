from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy.exc import IntegrityError

from database import get_db
from services.auth_service import RoleChecker
from schemas import vehicle_type as vt_schema
from crud import vehicle_type as crud_vt

router = APIRouter()


def _write_conflict(error: IntegrityError) -> HTTPException:
    # The DB remains authoritative, including races after a preflight lookup.
    # Inspect only known constraint identifiers; never expose SQL/parameters.
    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    prefix_conflict = (
        constraint == "uq_vehicle_types_code_prefix"
        or "UNIQUE constraint failed: vehicle_types.code_prefix" in str(error.orig)
    )
    detail = (
        "Tiền tố mã loại xe đã tồn tại. Hãy chọn mã khác."
        if prefix_conflict else "Tên hoặc tiền tố mã loại xe đã tồn tại."
    )
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


@router.get("", response_model=List[vt_schema.VehicleTypeResponse])
def read_vehicle_types(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Lấy danh sách các loại xe"""
    return crud_vt.get_vehicle_types(db, skip=skip, limit=limit)

@router.get("/{id}", response_model=vt_schema.VehicleTypeResponse)
def read_vehicle_type(id: int, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết một loại xe"""
    db_vt = crud_vt.get_vehicle_type(db, vt_id=id)
    if not db_vt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle Type not found")
    return db_vt

@router.post("", response_model=vt_schema.VehicleTypeResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(RoleChecker("manager"))])
def create_vehicle_type(vt_in: vt_schema.VehicleTypeCreate, db: Session = Depends(get_db)):
    """Tạo loại xe mới"""
    existing_vt = crud_vt.get_vehicle_type_by_name(db, name=vt_in.name)
    if existing_vt:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tên loại xe đã tồn tại.")

    try:
        return crud_vt.create_vehicle_type(db=db, vt_in=vt_in)
    except IntegrityError as error:
        raise _write_conflict(error) from error

@router.put("/{id}", response_model=vt_schema.VehicleTypeResponse,
            dependencies=[Depends(RoleChecker("manager"))])
def update_vehicle_type(id: int, vt_in: vt_schema.VehicleTypeUpdate, db: Session = Depends(get_db)):
    """Cập nhật thông tin loại xe"""
    db_vt = crud_vt.get_vehicle_type(db, vt_id=id)
    if not db_vt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle Type not found")
    if vt_in.name is not None:
        conflict = crud_vt.get_vehicle_type_by_name(db, name=vt_in.name)
        if conflict is not None and conflict.id != db_vt.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Tên loại xe đã tồn tại.",
            )

    try:
        return crud_vt.update_vehicle_type(db=db, db_vt=db_vt, vt_in=vt_in)
    except IntegrityError as error:
        raise _write_conflict(error) from error

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(RoleChecker("manager"))])
def delete_vehicle_type(id: int, db: Session = Depends(get_db)):
    """Xóa một loại xe"""
    db_vt = crud_vt.get_vehicle_type(db, vt_id=id)
    if not db_vt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle Type not found")
    
    try:
        crud_vt.delete_vehicle_type(db=db, db_vt=db_vt)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Loại xe đang được tham chiếu. Hãy ngừng sử dụng thay vì xóa.")
    return None
