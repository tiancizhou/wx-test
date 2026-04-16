import os


class WeChatSettings:
    TOKEN: str = os.getenv("WX_TOKEN", "qq5201314")
    APP_ID: str = os.getenv("WX_APP_ID", "wx9e7f92a7fad7e40f")
    APP_SECRET: str = os.getenv("WX_APP_SECRET", "3fc48aa59710c119b0dab6a8b725163f")
    ENCODING_AES_KEY: str = os.getenv("WX_ENCODING_AES_KEY", "wkTzbshp2Plx5QZ0uQVcKizai5F1ZCoEARuochQUAkQ")
    ADMIN_KEY: str = os.getenv("WX_ADMIN_KEY", "qq5201314")
    # 微信支付 V3
    MCH_ID: str = os.getenv("WX_MCH_ID", "")
    MCH_SERIAL_NO: str = os.getenv("WX_MCH_SERIAL_NO", "")
    MCH_PRIVATE_KEY_PATH: str = os.getenv("WX_MCH_PRIVATE_KEY_PATH", "")
    PAY_MOCK: bool = os.getenv("WX_PAY_MOCK", "true").lower() == "true"


settings = WeChatSettings()
