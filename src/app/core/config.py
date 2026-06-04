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

    # 缠论结构引擎根目录（可选；默认使用仓库内 vendored 计算库）
    chan_engine_root: str = ""

    # 分析记忆库（快照 / outcome）；与 APP_DATABASE_URL 独立，默认本地 SQLite
    analysis_db_url: str = "sqlite:///./data/analysis.db"
    # technical 成功后是否默认写入分析库（CLI --save / API save=true 可单独开启）
    analysis_save: bool = False

    # K 线对齐：utc=Binance 原生周期（默认）；beijing=北京时间 5m 聚合
    kline_mode: Literal["utc", "beijing"] = "utc"

    # FlowMarkets Crew：technical_only=仅技术分析师；full=市场→舆情→情绪→技术→综合→交易→组合
    flow_markets_mode: Literal["technical_only", "full"] = "technical_only"

    # Phase 7：结构引擎（默认 chanpy / structure-engine；chanlun_icl 仅对比）
    chan_structure_engine: Literal["structure-engine", "chanlun_icl"] = "structure-engine"
    chan_zs_algo: Literal["normal", "over_seg", "auto"] = "normal"
    chanlun_repo_root: str = ""

    @model_validator(mode="before")
    @classmethod
    def fallback_api_keys_from_env(cls, data: Any) -> Any:
        """未配置 APP_ 前缀时，可用 QWEN_API_KEY / DEEPSEEK_API_KEY / BAIDU_API_KEY 作为备用。"""
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if not (out.get("chan_engine_root") or "").strip():
            out["chan_engine_root"] = (
                (out.get("chanpy_root") or "").strip()
                or os.environ.get("APP_CHAN_ENGINE_ROOT", "").strip()
                or os.environ.get("APP_CHANPY_ROOT", "").strip()
            )
        if not (out.get("llm_api_key") or "").strip():
            out["llm_api_key"] = (
                os.environ.get("QWEN_API_KEY", "").strip()
                or os.environ.get("DEEPSEEK_API_KEY", "").strip()
            )
        if not (out.get("baidu_api_key") or "").strip():
            out["baidu_api_key"] = os.environ.get("BAIDU_API_KEY", "").strip()
        raw_mode = (
            (out.get("flow_markets_mode") or "").strip().lower()
            or os.environ.get("FLOW_MARKETS_MODE", "").strip().lower()
        )
        if raw_mode in ("technical_only", "full"):
            out["flow_markets_mode"] = raw_mode
        raw_engine = (
            (out.get("chan_structure_engine") or "").strip().lower()
            or os.environ.get("CHAN_STRUCTURE_ENGINE", "").strip().lower()
        )
        if raw_engine in ("structure-engine", "chanlun_icl"):
            out["chan_structure_engine"] = raw_engine
        raw_zs = (
            (out.get("chan_zs_algo") or "").strip().lower()
            or os.environ.get("CHAN_ZS_ALGO", "").strip().lower()
        )
        if raw_zs in ("normal", "over_seg", "auto"):
            out["chan_zs_algo"] = raw_zs
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
