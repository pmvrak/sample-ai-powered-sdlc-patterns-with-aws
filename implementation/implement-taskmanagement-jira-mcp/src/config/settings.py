# src/config/settings.py
import os
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    # JIRA Configuration
    jira_url: str = os.getenv("JIRA_URL", "")
    jira_username: str = os.getenv("JIRA_USERNAME", "")
    jira_api_token: str = os.getenv("JIRA_API_TOKEN", "")
    
    # MCP Server Configuration
    mcp_server_host: str = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    mcp_server_port: int = int(os.getenv("MCP_SERVER_PORT", "8000"))
    
    # AWS Configuration
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    
    class Config:
        env_file = ".env"

# Global settings instance
settings = Settings()

# Validation function
def validate_jira_config() -> bool:
    """Validate that all required JIRA configuration is present"""
    required_fields = [settings.jira_url, settings.jira_username, settings.jira_api_token]
    return all(field.strip() for field in required_fields)