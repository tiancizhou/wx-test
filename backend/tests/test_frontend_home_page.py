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


def test_home_page_is_a_lightweight_router_shell():
    content = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")

    assert "fonts.googleapis.com" not in content
    assert "fonts.gstatic.com" not in content
    assert "fastly.jsdelivr.net/npm/vue@3" not in content
    assert "fastly.jsdelivr.net/npm/vant@4" not in content
    assert "res.wx.qq.com/open/js/jweixin-1.6.0.js" not in content


def test_home_page_caches_last_role_for_direct_routing():
    content = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")

    assert "const LAST_ROLE_KEY = 'wx_last_role';" in content
    assert "localStorage.getItem(LAST_ROLE_KEY)" in content
    assert "localStorage.setItem(LAST_ROLE_KEY, user.role);" in content
    assert "CUSTOMER: '/customer'" in content
    assert "MERCHANT: '/merchant'" in content
