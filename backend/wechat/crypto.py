"""微信消息加解密库 (Python 3) — 从 WXBizMsgCrypt.py 迁移"""

import base64
import string
import random
import hashlib
import time
import struct
import socket

from Crypto.Cipher import AES
import xml.etree.cElementTree as ET


# ---- 错误码 ----
OK = 0
ValidateSignature_Error = -40001
ParseXml_Error = -40002
ComputeSignature_Error = -40003
IllegalAesKey = -40004
ValidateAppid_Error = -40005
EncryptAES_Error = -40006
DecryptAES_Error = -40007
IllegalBuffer = -40008


class FormatException(Exception):
    pass


def _sha1_sign(token: str, timestamp: str, nonce: str, encrypt: str) -> tuple[int, str | None]:
    try:
        items = sorted([token, timestamp, nonce, encrypt])
        sha = hashlib.sha1("".join(items).encode("utf-8"))
        return OK, sha.hexdigest()
    except Exception:
        return ComputeSignature_Error, None


def _extract_xml(xml_text: str) -> tuple[int, str | None, str | None]:
    try:
        root = ET.fromstring(xml_text)
        encrypt = root.find("Encrypt").text
        to_user = root.find("ToUserName").text
        return OK, encrypt, to_user
    except Exception:
        return ParseXml_Error, None, None


def _build_xml(encrypt: str, signature: str, timestamp: str, nonce: str) -> str:
    return (
        f"<xml>"
        f"<Encrypt><![CDATA[{encrypt}]]></Encrypt>"
        f"<MsgSignature><![CDATA[{signature}]]></MsgSignature>"
        f"<TimeStamp>{timestamp}</TimeStamp>"
        f"<Nonce><![CDATA[{nonce}]]></Nonce>"
        f"</xml>"
    )


class _PKCS7:
    BLOCK = 32

    @staticmethod
    def pad(data: bytes) -> bytes:
        n = _PKCS7.BLOCK - (len(data) % _PKCS7.BLOCK)
        if n == 0:
            n = _PKCS7.BLOCK
        return data + bytes([n]) * n

    @staticmethod
    def unpad(data: bytes) -> bytes:
        n = data[-1]
        if n < 1 or n > 32:
            n = 0
        return data[:-n]


class _AES:
    def __init__(self, key: bytes):
        self.key = key
        self.iv = key[:16]

    def encrypt(self, text: str, appid: str) -> tuple[int, str | None]:
        try:
            text_bytes = text.encode("utf-8")
            random_bytes = "".join(random.sample(string.ascii_letters + string.digits, 16)).encode("utf-8")
            length = struct.pack("I", socket.htonl(len(text_bytes)))
            raw = random_bytes + length + text_bytes + appid.encode("utf-8")
            raw = _PKCS7.pad(raw)
            cipher = AES.new(self.key, AES.MODE_CBC, self.iv).encrypt(raw)
            return OK, base64.b64encode(cipher).decode("utf-8")
        except Exception:
            return EncryptAES_Error, None

    def decrypt(self, ciphertext: str, appid: str) -> tuple[int, str | None]:
        try:
            plain = AES.new(self.key, AES.MODE_CBC, self.iv).decrypt(base64.b64decode(ciphertext))
        except Exception:
            return DecryptAES_Error, None
        try:
            content = plain[16:-plain[-1]]
            xml_len = socket.ntohl(struct.unpack("I", content[:4])[0])
            xml_content = content[4 : 4 + xml_len]
            from_appid = content[4 + xml_len :]
        except Exception:
            return IllegalBuffer, None
        if from_appid != appid.encode("utf-8"):
            return ValidateAppid_Error, None
        return OK, xml_content.decode("utf-8")


class WXBizMsgCrypt:
    """微信消息加解密对外接口"""

    def __init__(self, token: str, encoding_aes_key: str, app_id: str):
        self.token = token
        self.appid = app_id
        try:
            self.key = base64.b64decode(encoding_aes_key + "=")
            assert len(self.key) == 32
        except Exception:
            raise FormatException("EncodingAESKey 无效")

    def EncryptMsg(self, reply_msg: str, nonce: str, timestamp: str | None = None) -> tuple[int, str | None]:
        aes = _AES(self.key)
        ret, encrypt = aes.encrypt(reply_msg, self.appid)
        if ret != OK:
            return ret, None
        timestamp = timestamp or str(int(time.time()))
        ret, signature = _sha1_sign(self.token, timestamp, nonce, encrypt)
        if ret != OK:
            return ret, None
        return OK, _build_xml(encrypt, signature, timestamp, nonce)

    def DecryptMsg(self, post_data: str, msg_signature: str, timestamp: str, nonce: str) -> tuple[int, str | None]:
        ret, encrypt, _ = _extract_xml(post_data)
        if ret != OK:
            return ret, None
        ret, signature = _sha1_sign(self.token, timestamp, nonce, encrypt)
        if ret != OK:
            return ret, None
        if signature != msg_signature:
            return ValidateSignature_Error, None
        aes = _AES(self.key)
        return aes.decrypt(encrypt, self.appid)
