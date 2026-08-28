from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas import price_config as price_config_schema
from crud import price_config as crud_price_config

router = APIRouter()

_RATE_CONTRACT_FIELDS = {
    "vehicle_type_id",
    "ticket_type",
    "price",
    "effective_date",
    "is_active",
}


def _raise_if_active_rate_is_in_use(
    db: Session,
    *,
    db_config,
    changed_fields: set[str] | None = None,
) -> None:
    """Protect the fallback rate contract used by every open stay."""
    if changed_fields is not None and not (changed_fields & _RATE_CONTRACT_FIELDS):
        return
    if not db_config.is_active:
        return
    if crud_price_config.has_active_session_for_vehicle_type(
        db,
        vehicle_type_id=db_config.vehicle_type_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Bảng giá đang được dùng để tính phí cho phiên gửi xe "
                f"chưa check-out (ID bảng giá {db_config.id}). "
                "Hãy hoàn tất các phiên này trước khi thay đổi hoặc xóa bảng giá."
            ),
        )

@router.get("", response_model=List[price_config_schema.PriceConfigResponse])
def read_price_configs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Lấy danh sách cấu hình giá"""
    return crud_price_config.get_price_configs(db, skip=skip, limit=limit)

@router.get("/{id}", response_model=price_config_schema.PriceConfigResponse)
def read_price_config(id: int, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết một cấu hình giá"""
    db_config = crud_price_config.get_price_config(db, config_id=id)
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price config not found")
    return db_config

@router.post("", response_model=price_config_schema.PriceConfigResponse, status_code=status.HTTP_201_CREATED)
def create_price_config(config_in: price_config_schema.PriceConfigCreate, db: Session = Depends(get_db)):
    """Tạo cấu hình giá mới"""
    # Bất biến: mỗi loại xe chỉ có tối đa MỘT bảng giá active tại một thời điểm
    if config_in.is_active:
        active_config = crud_price_config.get_active_price_by_vehicle_type(
            db, vehicle_type_id=config_in.vehicle_type_id
        )
        if active_config:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Loại xe này đã có bảng giá đang áp dụng (ID {active_config.id}). "
                    "Hãy tắt bảng giá đó trước khi kích hoạt bảng giá mới."
                ),
            )

    return crud_price_config.create_price_config(db=db, config_in=config_in)

@router.put("/{id}", response_model=price_config_schema.PriceConfigResponse)
def update_price_config(id: int, config_in: price_config_schema.PriceConfigUpdate, db: Session = Depends(get_db)):
    """Cập nhật cấu hình giá (thay đổi giá hoặc trạng thái active)"""
    db_config = crud_price_config.get_price_config(db, config_id=id)
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price config not found")

    # Validate TRẠNG THÁI SAU MERGE, không chỉ transition false->true: một bảng
    # giá đang active đổi vehicle_type_id (payload không gửi is_active, hoặc gửi
    # is_active=true không đổi) vẫn phải bị chặn nếu loại xe đích đã có bảng giá
    # active khác — nếu không sẽ tạo hai bảng giá active cùng loại xe.
    update_data = config_in.model_dump(exclude_unset=True)
    changed_fields = {
        field
        for field, value in update_data.items()
        if value != getattr(db_config, field)
    }
    _raise_if_active_rate_is_in_use(
        db,
        db_config=db_config,
        changed_fields=changed_fields,
    )

    merged_vehicle_type_id = update_data.get("vehicle_type_id", db_config.vehicle_type_id)
    merged_is_active = update_data.get("is_active", db_config.is_active)

    if merged_is_active:
        conflict = crud_price_config.get_active_price_by_vehicle_type(
            db, vehicle_type_id=merged_vehicle_type_id, exclude_id=id
        )
        if conflict:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Loại xe này đã có bảng giá đang áp dụng khác (ID {conflict.id}). "
                    "Hãy tắt bảng giá đó trước khi kích hoạt bảng giá này cho loại xe đó."
                ),
            )

    return crud_price_config.update_price_config(db=db, db_config=db_config, config_in=config_in)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_price_config(id: int, db: Session = Depends(get_db)):
    """Xóa cấu hình giá"""
    db_config = crud_price_config.get_price_config(db, config_id=id)
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price config not found")

    _raise_if_active_rate_is_in_use(db, db_config=db_config)
    crud_price_config.delete_price_config(db=db, db_config=db_config)
    return None
