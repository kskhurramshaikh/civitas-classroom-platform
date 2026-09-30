from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://civitas:civitas@localhost:5432/civitas"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-3.5-sonnet"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    seed_token: str = ""  # set on Render only when running the one-off /admin/seed-demo endpoint

    class Config:
        env_file = ".env"


settings = Settings()
