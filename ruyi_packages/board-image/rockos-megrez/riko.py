
import re

from typing import List

from riko.core.models import RikoPkg, GithubUpstream


def rikoring(old_pkgs: List[RikoPkg], new_pkgs: List[RikoPkg]) -> None:
    """
    old toml stored in old_pkg, format new toml to new_pkg
    :param old_pkgs: old pkg list
    :param new_pkgs: new pkg list
    :return:
    """

    for p in new_pkgs:
        minor = p.version.minor

        img = p.get_manifest()[0]["distfiles"][0]["name"]
        new_minor = re.findall(r"sdcard-rockos-([\d]+)-[\d]+.img.zst", img)

        if new_minor and minor != new_minor[0]:
            p.version = p.get_version().replace(minor=new_minor[0])
