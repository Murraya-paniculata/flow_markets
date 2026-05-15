"""本地运行入口：在项目根目录执行 python -m app（需 PYTHONPATH=src 或从 src 上一级运行）。"""

if __name__ == "__main__":
    import os
    import uvicorn

    # 开发时常用：reload=True 便于改代码自动重载；调试断点时可改为 False
    # 只监听 src，避免 .venv / .git 等触发误重载
    root = os.path.abspath(os.curdir)
    src_dir = os.path.join(root, "src")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[src_dir] if os.path.isdir(src_dir) else [root],
    )
