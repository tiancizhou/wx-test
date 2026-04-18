from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
TEST_APP_ID = "wx9e7f92a7fad7e40f"


def test_home_page_requires_frontend_config_before_oauth():
    content = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")

    assert TEST_APP_ID not in content
    assert "let WX_APP_ID = '';" in content
    assert "fetch('/config/frontend')" in content
    assert "throw new Error('WX_APP_ID 未配置');" in content
