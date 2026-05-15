"""AI 任务结果实体（示例）。"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, gen_uuid
from app.db.models.base import TimestampMixin


class TaskResult(Base, TimestampMixin):
    """任务结果表：存储异步任务 ID 与结果。"""

    __tablename__ = "task_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    task_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
