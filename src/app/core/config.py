"""基于 Pydantic Settings 的配置管理，支持环境变量与 .env 分层加载。"""

import os
from functools import lru_cache
from typing import Any, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    全局配置。环境变量前缀 APP_，优先级：环境变量 > .env > 默认值。
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "staging", "production"] = "development"
    port: int = 8000
    log_level: str = "INFO"
    # 日志目录，按小时轮转；app.log 为全部级别，error.log 仅 ERROR
    log_dir: str = "./logs"

    database_url: str = "sqlite+aiosqlite:///./app.db"
    database_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"

    llm_api_key: str = ""
    llm_provider: str = "aliyun"
    llm_model: str = "qwen-plus"
    llm_base_url: str | None = None
    # 阿里云通义千问：cn / intl / finance
    llm_region: Literal["cn", "intl", "finance"] = "cn"
    llm_timeout: int = 600

    secret_key: str = "dev-secret-change-in-production"
    api_keys: str = ""  # 逗号分隔的合法 API Key，空表示不校验（仅开发）

    # 百度千帆搜索（AppBuilder）
    baidu_api_key: str = ""
    baidu_search_timeout: int = 30

    # 目录读取工具：若设置则仅允许列出该根目录下的路径，防目录穿越；空表示不限制
    tools_directory_read_root: str = ""

    # 深度调研 Demo：报告输出根目录（每次运行会在其下创建子目录）
    deep_research_output_dir: str = "./data/deep_research"

    # 缠论 chanpy 根目录（可选；默认使用仓库内 flow_markets/chanpy/）
    chanpy_root: str = ""

    @model_validator(mode="before")
    @classmethod
    def fallback_api_keys_from_env(cls, data: Any) -> Any:
        """未配置 APP_ 前缀时，可用 QWEN_API_KEY / DEEPSEEK_API_KEY / BAIDU_API_KEY 作为备用。"""
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if not (out.get("llm_api_key") or "").strip():
            out["llm_api_key"] = (
                os.environ.get("QWEN_API_KEY", "").strip()
                or os.environ.get("DEEPSEEK_API_KEY", "").strip()
            )
        if not (out.get("baidu_api_key") or "").strip():
            out["baidu_api_key"] = os.environ.get("BAIDU_API_KEY", "").strip()
        return out

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = ("DEBUG", "INFO", "WARNING", "ERROR")
        u = v.upper()
        if u not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return u

    def get_valid_api_keys(self) -> set[str]:
        """返回合法 API Key 集合。"""
        if not self.api_keys or not self.api_keys.strip():
            return set()
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    """获取单例配置，便于测试时覆盖。"""
    return Settings()
