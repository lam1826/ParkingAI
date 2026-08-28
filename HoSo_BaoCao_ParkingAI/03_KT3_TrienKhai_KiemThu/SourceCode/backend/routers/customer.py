from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas import customer as customer_schema
from crud import customer as crud_customer

router = APIRouter()

@router.get("", response_model=List[customer_schema.CustomerResponse])
def read_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Lấy danh sách khách hàng"""
    return crud_customer.get_customers(db, skip=skip, limit=limit)

@router.get("/{id}", response_model=customer_schema.CustomerResponse)
def read_customer(id: int, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết một khách hàng"""
    db_customer = crud_customer.get_customer(db, customer_id=id)
    if not db_customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return db_customer

@router.post("", response_model=customer_schema.CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_customer(customer_in: customer_schema.CustomerCreate, db: Session = Depends(get_db)):
    """Tạo khách hàng mới"""
    # Kiểm tra số điện thoại đã tồn tại chưa
    existing_customer = crud_customer.get_customer_by_phone(db, phone_number=customer_in.phone_number)
    if existing_customer:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Số điện thoại đã được đăng ký cho khách hàng khác.",
        )
    
    return crud_customer.create_customer(db=db, customer_in=customer_in)

@router.put("/{id}", response_model=customer_schema.CustomerResponse)
def update_customer(id: int, customer_in: customer_schema.CustomerUpdate, db: Session = Depends(get_db)):
    """Cập nhật thông tin khách hàng"""
    db_customer = crud_customer.get_customer(db, customer_id=id)
    if not db_customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    
    # Nếu có cập nhật số điện thoại, phải đảm bảo không trùng với người khác
    if (
        "phone_number" in customer_in.model_fields_set
        and customer_in.phone_number != db_customer.phone_number
    ):
        existing_customer = crud_customer.get_customer_by_phone(db, phone_number=customer_in.phone_number)
        if existing_customer:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Số điện thoại đã được đăng ký cho khách hàng khác.",
            )
            
    return crud_customer.update_customer(db=db, db_customer=db_customer, customer_in=customer_in)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(id: int, db: Session = Depends(get_db)):
    """Xóa một khách hàng"""
    db_customer = crud_customer.get_customer(db, customer_id=id)
    if not db_customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    if crud_customer.customer_has_vehicles(db, customer_id=id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Không thể xóa khách hàng đang có phương tiện; "
                "cần giữ liên kết để bảo toàn lịch sử."
            ),
        )
    if crud_customer.customer_has_monthly_passes(db, customer_id=id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Không thể xóa khách hàng đang có vé tháng; "
                "cần giữ liên kết để bảo toàn lịch sử."
            ),
        )
    
    crud_customer.delete_customer(db=db, db_customer=db_customer)
    return None
