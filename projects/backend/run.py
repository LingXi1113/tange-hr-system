"""后端服务入口（supervisor 约定：backend/.venv/bin/python run.py，端口固定 8100）。"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app.config["PORT"], debug=False)
