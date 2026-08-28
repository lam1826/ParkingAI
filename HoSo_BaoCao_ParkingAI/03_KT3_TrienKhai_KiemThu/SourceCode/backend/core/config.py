from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    """
    Lớp cấu hình trung tâm của ứng dụng.
    Pydantic sẽ tự động đọc các biến từ hệ điều hành hoặc file .env
    để map vào các thuộc tính này, đảm bảo type an toàn và không hard-code.
    """
    # Cấu hình JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    # Fail closed: có API key vẫn chưa đủ để gọi provider. Mỗi môi trường
    # phải bật AI một cách tường minh sau khi đã duyệt dữ liệu/chi phí.
    AI_ENABLED: bool = False
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.6-flash"
    AI_PROVIDER_TIMEOUT_MS: int = 85_000
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    MANAGER_REGISTRATION_CODE: str = ""
    ADMIN_REGISTRATION_CODE: str = ""
    AUTH_LOGIN_MAX_FAILURES: int = 10
    AUTH_LOGIN_WINDOW_SECONDS: int = 300
    AUTH_REGISTER_MAX_ATTEMPTS: int = 5
    AUTH_REGISTER_WINDOW_SECONDS: int = 3600
    
    # Chỉ định đọc từ file .env ở thư mục gốc
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

# Khởi tạo một instance duy nhất (Singleton) để import vào các service
settings = Settings()
