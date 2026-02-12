from typing import List

from riko.core.models import RikoPkg, RegexUpstream


def post_rikoring(old_pkgs: List[RikoPkg], new_pkgs: List[RikoPkg]) -> None:
    """
    old toml stored in old_pkg, format new toml to new_pkg
    :param old_pkgs: old pkg list
    :param new_pkgs: new pkg list
    :return:
    """

    for p in new_pkgs:
        for d in p.get_manifest()[0]["distfiles"]:
            urls = d["urls"]
            urls[0] = urls[0].replace("https://mirror.iscas.ac.cn/revyos/", "mirror://revyos/")
