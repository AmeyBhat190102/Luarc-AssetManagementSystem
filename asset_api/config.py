from pydantic_settings import BaseSettings, SettingsConfigDict #type: ignore


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    DB_MIN_CONN: int = 2
    DB_MAX_CONN: int = 10


settings = Settings()
