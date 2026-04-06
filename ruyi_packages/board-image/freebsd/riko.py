from typing import List

from riko.core.models import RikoPkg


def rikoring(old_pkgs: List[RikoPkg], new_pkgs: List[RikoPkg]) -> None:
    """
    old toml stored in old_pkg, format new toml to new_pkg
    :param old_pkgs: old pkg list
    :param new_pkgs: new pkg list
    :return:
    """
    urls = new_pkgs[0].get_manifest()[0]["distfiles"][0]["urls"]
    urls[0] = urls[0].replace("https://mirror.iscas.ac.cn/FreeBSD/releases", "https://download.freebsd.org")
