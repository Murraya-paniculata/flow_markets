"""任务结果仓储：语义化方法封装。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.task import TaskResult


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_result(self, task_id: str, status: str, result: str | None = None) -> TaskResult:
        row = TaskResult(task_id=task_id, status=status, result=result)
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_by_task_id(self, task_id: str) -> TaskResult | None:
        r = await self.session.execute(select(TaskResult).where(TaskResult.task_id == task_id))
        return r.scalars().one_or_none()
