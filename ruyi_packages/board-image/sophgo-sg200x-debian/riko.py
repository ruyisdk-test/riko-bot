import re
from typing import List, Dict

from riko.core.models import RikoPkg, GithubUpstream


def rikoring(old_pkgs: List[RikoPkg], new_pkgs: List[RikoPkg]) -> None:
    """
    old toml stored in old_pkg, format new toml to new_pkg
    :param old_pkgs: old pkg list
    :param new_pkgs: new pkg list
    :return:
    """

    upstream: GithubUpstream = new_pkgs[0].get_upstream()
    upstream_version: str = new_pkgs[0].get_upstream_version()
    assert upstream.source == "github"

    img, img_url = upstream.get_release_assert_substring("licheervnano_sd.img.lz4")

    new_pkgs[0].version = old_pkgs[0].version.parse(upstream_version[1:])

    new_toml = new_pkgs[0].get_manifest()[0]
    new_toml["blob"]["distfiles"] = [img]
    new_toml["distfiles"][0]["name"] = img
    new_toml["distfiles"][0]["urls"] = [img_url]

    new_pkgs[0].set_manifest_ready()
