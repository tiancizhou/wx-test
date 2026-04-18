import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIR / ".env"


def _load_env_file(env_file: Path = ENV_FILE) -> None:
    if not env_file.is_file():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


_load_env_file()


class WeChatSettings:
    TOKEN: str = os.getenv("WX_TOKEN", "")
    APP_ID: str = os.getenv("WX_APP_ID", "")
    APP_SECRET: str = os.getenv("WX_APP_SECRET", "")
    ENCODING_AES_KEY: str = os.getenv("WX_ENCODING_AES_KEY", "wkTzbshp2Plx5QZ0uQVcKizai5F1ZCoEARuochQUAkQ")
    ADMIN_KEY: str = os.getenv("WX_ADMIN_KEY", "qq5201314")
    # 微信支付 V3
    MCH_ID: str = os.getenv("WX_MCH_ID", "")
    MCH_SERIAL_NO: str = os.getenv("WX_MCH_SERIAL_NO", "")
    MCH_PRIVATE_KEY_PATH: str = os.getenv("WX_MCH_PRIVATE_KEY_PATH", "")
    API_V3_KEY: str = os.getenv("WX_API_V3_KEY", "")
    PLATFORM_SERIAL_NO: str = os.getenv("WX_PLATFORM_SERIAL_NO", "")
    PLATFORM_PUBLIC_KEY_PATH: str = os.getenv("WX_PLATFORM_PUBLIC_KEY_PATH", "")
    PAY_MOCK: bool = os.getenv("WX_PAY_MOCK", "true").lower() == "true"

    def validate_payment_config(self, require_platform_public_key: bool = False) -> None:
        if self.PAY_MOCK:
            return

        required_fields = [
            ("WX_MCH_ID", self.MCH_ID),
            ("WX_MCH_SERIAL_NO", self.MCH_SERIAL_NO),
            ("WX_MCH_PRIVATE_KEY_PATH", self.MCH_PRIVATE_KEY_PATH),
            ("WX_API_V3_KEY", self.API_V3_KEY),
        ]
        if require_platform_public_key:
            required_fields.append(("WX_PLATFORM_PUBLIC_KEY_PATH", self.PLATFORM_PUBLIC_KEY_PATH))

        missing = [env_name for env_name, value in required_fields if not value]
        if missing:
            raise RuntimeError(f"微信支付正式环境缺少必要配置: {', '.join(missing)}")

        missing_files = []
        key_file_fields = [("WX_MCH_PRIVATE_KEY_PATH", self.MCH_PRIVATE_KEY_PATH)]
        if require_platform_public_key:
            key_file_fields.append(("WX_PLATFORM_PUBLIC_KEY_PATH", self.PLATFORM_PUBLIC_KEY_PATH))

        for env_name, value in key_file_fields:
            if value and not Path(value).is_file():
                missing_files.append(env_name)

        if missing_files:
            raise RuntimeError(f"微信支付正式环境密钥文件不存在: {', '.join(missing_files)}")


settings = WeChatSettings()
