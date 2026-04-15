import os


class WeChatSettings:
    TOKEN: str = os.getenv("WX_TOKEN", "qq5201314")
    APP_ID: str = os.getenv("WX_APP_ID", "wx9e7f92a7fad7e40f")
    APP_SECRET: str = os.getenv("WX_APP_SECRET", "3fc48aa59710c119b0dab6a8b725163f")
    ENCODING_AES_KEY: str = os.getenv("WX_ENCODING_AES_KEY", "wkTzbshp2Plx5QZ0uQVcKizai5F1ZCoEARuochQUAkQ")
    ADMIN_KEY: str = os.getenv("WX_ADMIN_KEY", "wxmassage2026")
    # 微信支付
    MCH_ID: str = os.getenv("WX_MCH_ID", "")
    MCH_KEY: str = os.getenv("WX_MCH_KEY", "")
    PAY_MOCK: bool = os.getenv("WX_PAY_MOCK", "true").lower() == "true"


settings = WeChatSettings()
