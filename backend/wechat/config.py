import os


class WeChatSettings:
    TOKEN: str = os.getenv("WX_TOKEN", "qq5201314")
    APP_ID: str = os.getenv("WX_APP_ID", "")
    APP_SECRET: str = os.getenv("WX_APP_SECRET", "")
    ENCODING_AES_KEY: str = os.getenv("WX_ENCODING_AES_KEY", "")


settings = WeChatSettings()
