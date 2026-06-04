"""
AutoWealth AI 全局配置管理
"""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 加载环境变量
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


class Settings(BaseSettings):
    """应用配置类"""

    # API配置
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")

    # 本地LLM配置
    local_llm_url: str = Field(default="http://localhost:11434", alias="LOCAL_LLM_URL")
    local_llm_model: str = Field(default="llama2", alias="LOCAL_LLM_MODEL")

    # 数据配置
    data_cache_dir: str = Field(default="./data/cache", alias="DATA_CACHE_DIR")
    historical_data_years: int = Field(default=5, alias="HISTORICAL_DATA_YEARS")

    # 应用配置
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # 投资配置
    default_investment_amount: float = Field(default=10000.0, alias="DEFAULT_INVESTMENT_AMOUNT")
    risk_tolerance: str = Field(default="moderate", alias="RISK_TOLERANCE")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# 全局配置实例
settings = Settings()


def get_settings() -> Settings:
    """获取配置实例"""
    return settings
