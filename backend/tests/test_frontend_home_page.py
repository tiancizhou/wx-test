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


def test_home_page_reuses_verified_role_handoff_and_rechecks_cached_merchant_role():
    content = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")

    assert "const VERIFIED_ROLE_KEY = 'wx_verified_role';" in content
    assert "const VERIFIED_TOKEN_KEY = 'wx_verified_token';" in content
    assert "sessionStorage.setItem(VERIFIED_ROLE_KEY, user.role);" in content
    assert "sessionStorage.setItem(VERIFIED_TOKEN_KEY, token);" in content
    assert "if (token && lastRole === 'CUSTOMER' && ROLE_PAGES[lastRole])" in content
    assert "if (token && lastRole === 'MERCHANT')" in content
    assert "setStatus('正在确认商家身份...');" in content
