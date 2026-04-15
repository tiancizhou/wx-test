import os


class WeChatSettings:
    TOKEN: str = os.getenv("WX_TOKEN", "qq5201314")
    APP_ID: str = os.getenv("WX_APP_ID", "wx418d84117fe16bcc")
    APP_SECRET: str = os.getenv("WX_APP_SECRET", "6bfb1b36386d11e4efba9d2fd2ef38f9")
    ENCODING_AES_KEY: str = os.getenv("WX_ENCODING_AES_KEY", "wkTzbshp2Plx5QZ0uQVcKizai5F1ZCoEARuochQUAkQ")


settings = WeChatSettings()
