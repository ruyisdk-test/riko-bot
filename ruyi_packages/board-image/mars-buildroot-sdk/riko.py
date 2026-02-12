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

    # files
    mars_cm_sd, mars_cm_sd_url = upstream.get_release_assert_regex(f"mars-cm_debian-desktop_sdk-v[\\d]+\\.[\\d]+\\.[\\d]+_cm4-io-board_sdcard_v{upstream_version[1:]}.img.zip")
    mars_sd, mars_sd_url = upstream.get_release_assert_regex(f"mars_debian-desktop_sdk-v[\\d]+\\.[\\d]+\\.[\\d]+_sdcard_v{upstream_version[1:]}.img.zip")

    # version
    sub_ver = re.findall(rf"mars-cm_debian-desktop_sdk-v(\d+\.\d+\.\d+)_cm4-io-board_sdcard_v{upstream_version[1:]}.img.zip", mars_cm_sd)
    sub_ver2 = re.findall(rf"mars_debian-desktop_sdk-v(\d+\.\d+\.\d+)_sdcard_v{upstream_version[1:]}.img.zip", mars_sd)
    assert len(sub_ver) == 1
    assert len(sub_ver2) == 1
    assert sub_ver[0] == sub_ver2[0]

    new_ver = new_pkgs[0].get_version().parse(f"{upstream_version[1:]}+{sub_ver[0]}")
    old_ver = old_pkgs[0].get_version()

    for i in range(0, len(new_pkgs)):
        new_pkgs[i].version = new_ver
        new_toml = new_pkgs[i].get_manifest()[0]
        new_toml["metadata"]["desc"] = (
            new_toml["metadata"]["desc"].replace(old_pkgs[0].get_upstream_version()[1:], new_pkgs[0].get_upstream_version()[1:])
                                        .replace(old_ver.build, sub_ver[0]))

        if new_pkgs[i].get_combo() == "debian-desktop-sdk-milkv-mars-sd":
            new_toml["blob"]["distfiles"] = [mars_sd]
            new_toml["distfiles"][0]["name"] = mars_sd
            new_toml["distfiles"][0]["urls"] = [mars_sd_url]
        elif new_pkgs[i].get_combo() == "debian-desktop-sdk-milkv-mars-cm-sd":
            new_toml["blob"]["distfiles"] = [mars_cm_sd]
            new_toml["distfiles"][0]["name"] = mars_cm_sd
            new_toml["distfiles"][0]["urls"] = [mars_cm_sd_url]
        else:
            raise RuntimeError(f"Unknown combo {old_pkgs[i].get_combo()}")

        new_pkgs[i].set_manifest_ready()
