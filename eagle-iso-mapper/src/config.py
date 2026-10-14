from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    # Default paths (relative to project root)
    SSSOM_CONFIG_PATH: Path = Path("src/mapping/eagle_iso_sssom.yaml")
    MAPPING_CONFIG_PATH: Path = Path("src/mapping/eagle_iso_sssom.yaml")
    LINKML_MODEL_PATH: Path = Path("src/model/eagle-iso-mapping.linkml.yaml")

    # Allows overriding via .env file if present
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# Initialize global config object
settings = Settings()
