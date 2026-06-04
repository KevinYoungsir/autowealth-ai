"""
AutoWealth AI 鍏ㄥ眬閰嶇疆绠＄悊
"""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# 鍔犺浇鐜鍙橀噺
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


class Settings(BaseSettings):
    """搴旂敤閰嶇疆绫?""

    # API閰嶇疆
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")

    # 鏈湴LLM閰嶇疆
    local_llm_url: str = Field(default="http://localhost:11434", alias="LOCAL_LLM_URL")
    local_llm_model: str = Field(default="llama2", alias="LOCAL_LLM_MODEL")

    # 鏁版嵁閰嶇疆
    data_cache_dir: str = Field(default="./data/cache", alias="DATA_CACHE_DIR")
    historical_data_years: int = Field(default=5, alias="HISTORICAL_DATA_YEARS")

    # 搴旂敤閰嶇疆
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # 鎶曡祫閰嶇疆
    default_investment_amount: float = Field(default=10000.0, alias="DEFAULT_INVESTMENT_AMOUNT")
    risk_tolerance: str = Field(default="moderate", alias="RISK_TOLERANCE")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# 鍏ㄥ眬閰嶇疆瀹炰緥
settings = Settings()


def get_settings() -> Settings:
    """鑾峰彇閰嶇疆瀹炰緥"""
    return settings
