import base64

from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from yarl import URL

from logger import Logger, set_log_filename

from . import get_ua
from .classes import ClassContainer
from .exception import APIError
from .schema import AccountInfo, AccountSex
from .session import SessionWraper

# 接口-web端登录
API_LOGIN_WEB = "https://passport2.chaoxing.com/fanyalogin"

# 接口-激活二维码key并返回二维码图片
API_QRCREATE = "https://passport2.chaoxing.com/createqr"

# 接口-web端二维码登录
API_QRLOGIN = "https://passport2.chaoxing.com/getauthstatus"

# 接口-课程列表
API_CLASS_LST = "https://mooc1-api.chaoxing.com/mycourse/backclazzdata"

# 接口-SSO二步登录 (用作获取登录信息)
API_SSO_LOGIN = "https://sso.chaoxing.com/apis/login/userLogin4Uname.do"

# SSR页面-登录 用于提取二维码key
PAGE_LOGIN = "https://passport2.chaoxing.com/login"

# 二维码登录 url 
URL_QRLOGIN = "https://passport2.chaoxing.com/toauthlogin"

class ChaoXingAPI:
    """学习通根接口类
    """
    logger: Logger          # 日志记录器
    session: SessionWraper  # HTTP 会话封装
    acc: AccountInfo        # 用户账号信息
    # 二维码登录用
    qr_uuid: str
    qr_enc: str

    def __init__(self) -> None:
        """constructor
        Args:
            session: HTTP 会话封装对象
        """
        self.logger = Logger("RootAPI")
        self.session = SessionWraper()

    def login_passwd(self, phone: str, passwd: str) -> tuple[bool, dict]:
        """以 web 方式使用手机号+密码账号
        Args:
            phone: 手机号
            passwd: 登录密码
        """
        KEY = b"u2oh6Vu^HWe4_AES"
        # 开始加密参数
        cryptor = AES.new(KEY, AES.MODE_CBC, KEY)
        phone = base64.b64encode(cryptor.encrypt(pad(phone.encode(), 16))).decode()
        cryptor = AES.new(KEY, AES.MODE_CBC, KEY)
        passwd = base64.b64encode(cryptor.encrypt(pad(passwd.encode(), 16))).decode()

        resp = self.session.post(
            API_LOGIN_WEB,
            data={
                "fid": -1,
                "uname": phone,
                "password": passwd,
                "t": "true",
                "forbidotherlogin": 0,
                "validate": "",
            },
        )
        resp.raise_for_status()
        json_content = resp.json()
        
        if json_content.get("status") != True:
            return False, json_content
        return True, json_content

    def qr_get(self) -> None:
        """获取用于二维码登录的 key
        """
        self.session.cookies.clear()
        resp = self.session.get(
            PAGE_LOGIN,
            headers={
                "User-Agent": get_ua("web"),    # 这里不可以用移动端 UA 否则鉴权失败
            },
        )
        resp.raise_for_status()
        html = BeautifulSoup(resp.text, "lxml")
        self.qr_uuid = html.find("input", id="uuid")["value"]
        self.qr_enc = html.find("input", id="enc")["value"]

        # 激活 qr 并忽略返回的图片 bin
        resp = self.session.get(API_QRCREATE, params={"uuid": self.qr_uuid, "fid": -1})
        resp.raise_for_status()

    def qr_geturl(self) -> str:
        """合成二维码内容 url
        Returns:
            str: 登录二维码内容 url
        """
        return str(URL(URL_QRLOGIN).with_query(
            uuid=self.qr_uuid,
            enc=self.qr_enc,
            xxtrefer="",
            clientid="",
            mobiletip=""
        ))

    def login_qr(self) -> dict:
        """尝试使用二维码登录
        """
        resp = self.session.post(
            API_QRLOGIN,
            data={
                "enc": self.qr_enc,
                "uuid": self.qr_uuid,
            },
        )
        resp.raise_for_status()
        content_json = resp.json()
        return content_json

    def accinfo(self) -> bool:
        """获取登录用户信息 同时判断会话有效
        Returns:
            bool: 会话是否有效
        """
        resp = self.session.get(API_SSO_LOGIN)
        resp.raise_for_status()
        json_content = resp.json()
        
        if json_content.get("result") == 0:
            return False
        
        # 开始解析数据
        self.acc = AccountInfo(
            puid=json_content["msg"]["puid"],
            name=json_content["msg"]["name"],
            sex=AccountSex(json_content["msg"]["sex"]),
            phone=json_content["msg"]["phone"],
            school=json_content["msg"]["schoolname"],
            stu_id=json_content["msg"].get("uname"),  # 容许不存在学号的情况
        )
        set_log_filename(self.acc.phone)
        self.logger.info(f"账号登录成功 {self.acc}")
        return True

    def fetch_classes(self) -> ClassContainer:
        """拉取所有课程
        Returns:
            ClassContainer: 课程容器对象
        """
        resp = self.session.get(API_CLASS_LST)
        resp.raise_for_status()
        json_content = resp.json()
        
        if json_content.get("result") != 1:
            self.logger.error(f"课程列表拉取失败")
            raise APIError
        
        self.logger.info(f"课程列表拉取成功 共 {len(json_content['channelList'])} 个")
        return ClassContainer(session=self.session, acc=self.acc, classes_lst=json_content["channelList"])


__all__ = ["ChaoXingAPI"]
