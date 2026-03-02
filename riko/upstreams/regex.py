# riko/upstreams/regex.py - 正则表达式上游源
"""
从网页中提取文件信息（名称、URL）的上游源实现

使用场景：
- 从发布页面的 HTML 中提取下载链接
- 通过正则表达式匹配文件名和 URL
- 支持子字符串过滤和正则表达式过滤
"""

import http.client  # HTTP 客户端（低级别）
import logging
import os  # 操作系统接口（环境变量）
import re  # 正则表达式
import urllib.parse  # URL 解析
import urllib.request  # URL 请求

from typing import ClassVar, List, Tuple  # 类型注解

from .upstream import Upstream  # 上游源基类

logger = logging.getLogger(__name__)


def _get_proxy_handler():
    """
    获取代理处理器

    通过检查 HTTP_PROXY 和 HTTPS_PROXY 环境变量来配置代理

    :return: urllib.request.ProxyHandler 对象，如果没有配置代理则返回 None
    """
    # 检查环境变量中的代理设置
    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')

    proxies = {}
    if http_proxy:
        proxies['http'] = http_proxy
        logger.debug(f"Using HTTP proxy: {http_proxy}")
    if https_proxy:
        proxies['https'] = https_proxy
        logger.debug(f"Using HTTPS proxy: {https_proxy}")

    if proxies:
        return urllib.request.ProxyHandler(proxies)
    return None


class RegexUpstream(Upstream):
    """
    正则表达式上游源类

    工作流程：
    1. 发送 HTTP 请求获取网页内容
    2. 使用正则表达式匹配文件名
    3. 支持子字符串过滤
    4. 支持正则表达式二次过滤
    5. 返回文件名和 URL 元组

    使用示例：
    ```python
    upstream = RegexUpstream(
        base_url="https://example.com/releases",
        base_re=r"href=\"([^\"]+\\.tar\\.gz)\"",
        file_url="https://example.com/releases/index.html",
        file_re=r"href=\"([^\"]+\\.tar\\.gz)\""
    )
    files = upstream.get_release_asserts()
    ```
    """

    source: ClassVar[str] = "regex"  # 上游源类型标识

    def __init__(self, base_url: str, base_re: str, file_url: str, file_re: str) -> None:
        """
        初始化 RegexUpstream

        :param base_url: 基础 URL（暂未使用，保留用于未来扩展）
        :param base_re: 基础正则表达式（暂未使用）
        :param file_url: 要获取的网页 URL
        :param file_re: 用于匹配文件名的正则表达式

        """
        self._base_url = base_url          # 基础 URL（未使用）
        self._base_regex = base_re        # 基础正则（未使用）
        self._file_url = file_url          # 文件列表页面 URL
        self._file_regex = file_re        # 提取文件名的正则表达式

        # 实例变量
        self._ready = False               # 是否已加载网页内容
        self._text = ""                   # 网页文本内容
        self._asserts: List[str] = []     # 匹配到的文件名列表

    def _file_name_and_url(self, f: str) -> Tuple[str, str]:
        """
        生成文件名和完整 URL 的元组

        :param f: 文件名（相对路径）
        :return: (文件名, 完整URL) 元组
        """
        return f, urllib.parse.urljoin(self._file_url, f)

    # 获取发布文件列表
    def get_release_asserts(self) -> List[str]:
        """
        从网页获取所有匹配的文件名

        工作流程：
        1. 检查是否已加载（避免重复请求）
        2. 发送 HTTP GET 请求
        3. 检查 HTTP 状态码
        4. 解析响应内容为文本
        5. 使用正则表达式匹配文件名

        :return: 文件名列表

        """
        # 如果已加载，直接返回缓存
        if self._ready:
            return self._asserts

        # 配置代理
        proxy_handler = _get_proxy_handler()
        opener = urllib.request.build_opener(proxy_handler) if proxy_handler else urllib.request.build_opener()
        urllib.request.install_opener(opener)

        # 发送 HTTP GET 请求
        # urllib.request.urlopen() 返回 HTTPResponse 对象
        resp: http.client.HTTPResponse = opener.open(self._file_url, timeout=30.0)

        # 检查 HTTP 状态码
        # http.client.OK = 200
        if resp.status != http.client.OK:
            raise RuntimeError(f"url {self._file_url} returned status code {resp.status}: "
                               f"{http.client.responses[resp.status]}")

        # 读取响应内容并解码
        # .read(): 读取所有字节
        # .decode(): 转换为字符串（默认 UTF-8）
        self._text = resp.read().decode()

        # 使用正则表达式匹配文件名
        # re.findall(): 返回所有匹配结果的列表
        self._asserts = re.findall(self._file_regex, self._text)

        self._ready = True  # 标记已加载

        return self._asserts

    # 过滤方法：子字符串匹配
    def get_release_asserts_substring(self, substr: str) -> List[Tuple[str, str]]:
        """
        使用子字符串过滤文件列表

        :param substr: 要匹配的子字符串（例如："sg2042"）
        :return: 匹配的 (文件名, URL) 元组列表

        使用场景：
        从多个文件中筛选出包含特定关键字（如板卡型号）的文件

        """
        r = []

        for f in self.get_release_asserts():
            # 检查文件名是否包含子字符串
            if substr in f:
                # 生成 (文件名, URL) 元组并添加到结果列表
                r.append(self._file_name_and_url(f))

        return r

    def get_release_assert_substring(self, substr: str) -> Tuple[str, str]:
        """
        使用子字符串过滤，并确保只有一个结果

        :param substr: 要匹配的子字符串
        :return: (文件名, URL) 元组
        :raises AssertionError: 如果匹配结果不等于 1 个

        Python 特殊语法：
        - assert: 断言（类似于 Java's assert）
        - 如果条件为 False，抛出 AssertionError
        """
        r = self.get_release_asserts_substring(substr)

        # 确保只有一个匹配结果
        assert len(r) == 1, f"Expected 1 result, got {len(r)}"
        return r[0]

    # 过滤方法：正则表达式匹配
    def get_release_asserts_regex(self, pattern: str) -> List[Tuple[str, str]]:
        """
        使用正则表达式过滤文件列表

        :param pattern: 正则表达式模式（例如：r".*sdcard.*\\.img\\.xz"）
        :return: 匹配的 (文件名, URL) 元组列表

        使用场景：
        从多个文件中筛选出符合特定模式的文件（如 SD 卡镜像）

        Python 特殊语法：
        - re.search(): 在字符串中搜索正则表达式
        - 返回 Match 对象或 None
        """
        r = []

        for f in self.get_release_asserts():
            # 使用正则表达式搜索
            if re.search(pattern, f):
                r.append(self._file_name_and_url(f))

        return r

    def get_release_assert_regex(self, pattern: str) -> Tuple[str, str]:
        """
        使用正则表达式过滤，并确保只有一个结果

        :param pattern: 正则表达式模式
        :return: (文件名, URL) 元组
        :raises AssertionError: 如果匹配结果不等于 1 个

        """
        r = self.get_release_asserts_regex(pattern)

        # 确保只有一个匹配结果
        assert len(r) == 1, f"Expected 1 result, got {len(r)}"
        return r[0]
