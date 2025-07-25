import pytest
from fastapi.testclient import TestClient

# --- 重要假设 ---
# 假设您的 FastAPI 应用实例名为 `app`，且位于项目根目录的 `main.py` 文件中。
# 如果您的应用实例在其他位置（例如 `web/app.py`），请相应地修改下面的导入语句。
from web.main import app
# --- 测试客户端 ---
# 通过 `TestClient` 类创建一个测试客户端，以便在测试中进行 HTTP 请求。


@pytest.fixture(scope="session")
def client():
    """
    提供一个在测试会话期间持续存在的 TestClient 实例。
    """
    with TestClient(app) as c:
        yield c
