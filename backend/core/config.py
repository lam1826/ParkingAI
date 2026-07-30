from pydantic_settings import BaseSettings, SettingsConfigDict

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
    GEMINI_API_KEY: str
    
    # Chỉ định đọc từ file .env ở thư mục gốc
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# Khởi tạo một instance duy nhất (Singleton) để import vào các service
settings = Settings()