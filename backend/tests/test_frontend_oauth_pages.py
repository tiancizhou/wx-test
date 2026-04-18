from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
TEST_APP_ID = "wx9e7f92a7fad7e40f"


def test_customer_and_merchant_pages_do_not_hardcode_test_app_id():
    for page in ("customer.html", "merchant.html"):
        content = (FRONTEND_DIR / page).read_text(encoding="utf-8")
        assert TEST_APP_ID not in content


def test_customer_and_merchant_pages_require_frontend_config_before_oauth():
    for page in ("customer.html", "merchant.html"):
        content = (FRONTEND_DIR / page).read_text(encoding="utf-8")
        assert "let WX_APP_ID = '';" in content
        assert "fetch('/config/frontend')" in content
        assert "throw new Error('WX_APP_ID 未配置');" in content
