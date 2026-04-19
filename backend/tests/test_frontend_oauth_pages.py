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


def test_customer_and_merchant_pages_do_not_load_google_fonts():
    for page in ("customer.html", "merchant.html"):
        content = (FRONTEND_DIR / page).read_text(encoding="utf-8")
        assert "fonts.googleapis.com" not in content
        assert "fonts.gstatic.com" not in content


def test_customer_and_merchant_pages_validate_server_role_before_syncing_cache():
    expected_roles = {
        "customer.html": "CUSTOMER",
        "merchant.html": "MERCHANT",
    }

    for page, role in expected_roles.items():
        content = (FRONTEND_DIR / page).read_text(encoding="utf-8")
        assert "async function ensureExpectedRole(expectedRole)" in content
        assert "function consumeVerifiedRole(expectedRole)" in content
        assert "sessionStorage.getItem('wx_verified_role')" in content
        assert "sessionStorage.getItem('wx_verified_token')" in content
        assert "const me = await api('/me');" in content
        assert "localStorage.setItem('wx_last_role', me.role);" in content
        assert "location.replace(rolePages[me.role]);" in content
        assert f"ensureExpectedRole('{role}')" in content
        assert f"localStorage.setItem('wx_last_role', '{role}');" not in content
        assert "localStorage.removeItem('wx_last_role');" in content


def test_customer_page_parallelizes_role_check_with_goods_loading():
    content = (FRONTEND_DIR / "customer.html").read_text(encoding="utf-8")

    assert "const roleCheck = ensureExpectedRole('CUSTOMER');" in content
    assert "const goodsRequest = loadGoods();" in content
    assert "const role = await roleCheck;" in content
    assert "await goodsRequest;" in content


def test_customer_page_prioritizes_goods_and_defers_secondary_tabs():
    content = (FRONTEND_DIR / "customer.html").read_text(encoding="utf-8")

    assert "function deferNonCriticalLoad(task)" in content
    assert "async function ensureOrdersLoaded(force = false)" in content
    assert "async function ensureProfileLoaded(force = false)" in content
    assert "async function ensureMessageCenterReady(force = false)" in content
    assert "async function warmCustomerDeferredData()" in content
    assert "deferNonCriticalLoad(warmCustomerDeferredData);" in content
    assert "const goodsRequest = loadGoods();" in content
    assert "await goodsRequest;" in content
    assert """await Promise.all([
          loadGoods(),
          loadOrders(),
          loadMe(),
          loadConversationSummary(),
          loadMerchantContacts(),
        ]);""" not in content


def test_merchant_page_prioritizes_orders_and_defers_secondary_tabs():
    content = (FRONTEND_DIR / "merchant.html").read_text(encoding="utf-8")

    assert "function deferNonCriticalLoad(task)" in content
    assert "async function ensureOrdersLoaded(force = false)" in content
    assert "async function ensureGoodsLoaded(force = false)" in content
    assert "async function ensureStatsLoaded(force = false)" in content
    assert "async function ensureConversationWorkspaceReady(force = false)" in content
    assert "async function warmMerchantDeferredData()" in content
    assert "deferNonCriticalLoad(warmMerchantDeferredData);" in content
    assert "await ensureOrdersLoaded();" in content
    assert """await Promise.all([
          loadOrders(),
          loadGoods(),
          loadStats(),
          loadConversations(),
          loadMerchantContacts(),
        ]);""" not in content
