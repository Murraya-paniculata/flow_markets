"""修复版目录读取工具：递归列出目录内容，修复 directory 为 '.' 时文件名中点号被错误替换的问题。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.observability.logging import get_logger

logger = get_logger(__name__)


class DirectoryReadToolSchema(BaseModel):
    """目录读取工具的输入（需提供 directory 时使用）。"""

    directory: str = Field(..., description="要列出内容的目录路径，必填。")


class FixedDirectoryReadToolSchema(BaseModel):
    """无参 schema，用于构造时已指定 directory 的实例。"""

    pass


class FixedDirectoryReadTool(BaseTool):
    """
    修复版目录读取工具。递归列出目录下的文件路径。
    修复了原版在 directory 为 '.' 时，文件名中的点号被错误 replace 的问题，
    使用 os.path.relpath 正确计算相对路径。
    可选通过 APP_TOOLS_DIRECTORY_READ_ROOT 限制可访问的根目录，防止目录穿越。
    """

    name: str = "List files in directory"
    description: str = (
        "A tool that can be used to recursively list a directory's content. "
        "Returns file paths relative to the given directory."
    )
    args_schema: type[BaseModel] = DirectoryReadToolSchema
    directory: str | None = None

    def __init__(self, directory: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if directory is not None:
            self.directory = directory
            self.description = f"A tool that can be used to list {directory}'s content."
            self.args_schema = FixedDirectoryReadToolSchema
            if hasattr(self, "_generate_description"):
                self._generate_description()

    def _run(self, **kwargs: Any) -> str:
        directory: str | None = kwargs.get("directory", self.directory)
        if not directory:
            raise ValueError("directory 必须提供：通过参数传入或在构造时指定。")

        directory = os.path.normpath(directory)
        if directory.endswith("/"):
            directory = directory[:-1]
        abs_directory = os.path.abspath(directory)

        # 可选：限制在配置的根目录下，防止目录穿越
        root_cfg = get_settings().tools_directory_read_root
        if root_cfg:
            root_abs = os.path.abspath(root_cfg)
            if not abs_directory.startswith(root_abs):
                logger.warning(
                    "directory_read_outside_root",
                    directory=directory,
                    allowed_root=root_cfg,
                )
                raise ValueError(
                    f"目录必须在允许的根目录下：{root_cfg}，当前：{directory}"
                )

        if not os.path.isdir(directory):
            raise ValueError(f"路径不是目录或不存在：{directory}")

        files_list: list[str] = []
        for root, _dirs, files in os.walk(directory):
            for filename in files:
                full_path = os.path.join(root, filename)
                abs_full_path = os.path.abspath(full_path)
                rel_path = os.path.relpath(abs_full_path, abs_directory)
                if directory != "." and directory != os.path.curdir:
                    file_path = os.path.join(directory, rel_path).replace(os.path.sep, "/")
                else:
                    file_path = rel_path.replace(os.path.sep, "/")
                files_list.append(file_path)

        logger.debug("directory_read_done", directory=directory, count=len(files_list))
        if not files_list:
            return "File paths: \n(空目录)"
        return "File paths: \n- " + "\n- ".join(files_list)
