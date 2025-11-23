from pydantic_settings import BaseSettings
from typing import List
from pydantic import Field, computed_field
import os


class Settings(BaseSettings):
    database_url: str = Field(..., description="PostgreSQL database URL")
    jwt_secret: str = Field(..., min_length=32, description="JWT secret key (minimum 32 characters)")
    kafka_bootstrap_servers: str = Field(default="localhost:9092", description="Kafka bootstrap servers")
    admin_api_key: str = Field(default="", description="Admin API key for admin endpoints")
    cors_origins_str: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        alias="CORS_ORIGINS",
        description="Comma-separated list of allowed CORS origins"
    )
    rate_limit_requests: int = Field(default=100, description="Number of requests allowed per rate limit period")
    rate_limit_period: str = Field(default="minute", description="Rate limit period (minute, hour, etc.)")
    
    @computed_field
    @property
    def cors_origins(self) -> List[str]:
        """Parse comma-separated CORS origins into a list"""
        if not self.cors_origins_str:
            return []
        return [origin.strip() for origin in self.cors_origins_str.split(",") if origin.strip()]
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        populate_by_name = True  # Allow both field name and alias


settings = Settings()

