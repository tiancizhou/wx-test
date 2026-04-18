import importlib.util
import uuid
from pathlib import Path


CONFIG_SOURCE = (Path(__file__).resolve().parents[1] / "wechat" / "config.py").read_text(encoding="utf-8")
ENV_KEYS = [
    "WX_TOKEN",
    "WX_APP_ID",
    "WX_APP_SECRET",
    "WX_ENCODING_AES_KEY",
    "WX_ADMIN_KEY",
    "WX_MCH_ID",
    "WX_MCH_SERIAL_NO",
    "WX_MCH_PRIVATE_KEY_PATH",
    "WX_API_V3_KEY",
    "WX_PLATFORM_SERIAL_NO",
    "WX_PLATFORM_PUBLIC_KEY_PATH",
    "WX_PAY_MOCK",
]


def import_config_module(tmp_path: Path, env_content: str | None = None):
    backend_dir = tmp_path / "backend"
    wechat_dir = backend_dir / "wechat"
    wechat_dir.mkdir(parents=True)
    (wechat_dir / "config.py").write_text(CONFIG_SOURCE, encoding="utf-8")

    if env_content is not None:
        (backend_dir / ".env").write_text(env_content, encoding="utf-8")

    module_name = f"test_wechat_config_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, wechat_dir / "config.py")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def clear_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_settings_load_backend_dotenv_on_import(tmp_path, monkeypatch):
    clear_env(monkeypatch)

    module = import_config_module(
        tmp_path,
        env_content="WX_APP_ID=wx-from-dotenv\nWX_PAY_MOCK=false\n",
    )

    assert module.settings.APP_ID == "wx-from-dotenv"
    assert module.settings.PAY_MOCK is False


def test_explicit_env_overrides_backend_dotenv(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv("WX_APP_ID", "wx-from-env")

    module = import_config_module(tmp_path, env_content="WX_APP_ID=wx-from-dotenv\n")

    assert module.settings.APP_ID == "wx-from-env"


def test_missing_backend_dotenv_keeps_existing_defaults(tmp_path, monkeypatch):
    clear_env(monkeypatch)

    module = import_config_module(tmp_path)

    assert module.settings.APP_ID == ""
    assert module.settings.PAY_MOCK is True
