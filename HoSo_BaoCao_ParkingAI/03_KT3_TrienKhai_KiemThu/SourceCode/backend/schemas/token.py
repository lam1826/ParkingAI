from typing import Optional
from pydantic import BaseModel

class Token(BaseModel):
    """
    Schema định nghĩa cấu trúc trả về khi đăng nhập thành công.
    """
    access_token: str
    token_type: str

class TokenData(BaseModel):
    """
    Schema định nghĩa cấu trúc dữ liệu payload được trích xuất từ JWT token.
    """
    username: Optional[str] = None