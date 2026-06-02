from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    # Default paths (relative to project root)
    MAPPING_CONFIG_PATH: Path = Path("src/model/eagle-mapping.yaml")
    LINKML_MODEL_PATH: Path = Path("src/model/eagle-lcml-mapping.linkml.yaml")

    # Allows overriding via .env file if present
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# Initialize global config object
settings = Settings()