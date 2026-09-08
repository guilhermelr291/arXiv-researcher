from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str
    voyage_api_key: str = Field(min_length=1)
    database_url: str
    mock_arxiv_id: str = ""
    api_host: str = "127.0.0.1"
    api_port: int = 8001
    research_timeout_seconds: int = 120
