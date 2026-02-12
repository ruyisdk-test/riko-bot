import semver

from typing import List, Dict, Tuple

from riko.core.models import RikoPkg, GithubUpstream


def rikoring(old_pkgs: List[RikoPkg], new_pkgs: List[RikoPkg]) -> None:

    # First, get new toml, some items such as upstream_version will automatically set.
    # NOTE that `old_pkgs` is read only, do not modify it to prevent unexpected result
    # Note that this package only has one combo
    new_toml: Dict = new_pkgs[0].get_manifest()[0]
    upstream: GithubUpstream = new_pkgs[0].get_upstream()
    upstream_version: str = new_pkgs[0].get_upstream_version()

    assert upstream.source == "github"

    # Second, generate new version
    # Upstream version is ruyi version
    new_pkgs[0].version = semver.Version.parse(upstream_version)

    # Third, edit metadata.desc
    new_toml["metadata"]["desc"] = (
        new_toml["metadata"]["desc"].replace(old_pkgs[0].get_upstream_version(), new_pkgs[0].get_upstream_version()))

    # See: https://github.com/ruyisdk/support-matrix/issues/353
    # Fourth, get file
    # assets = upstream.get_release_asserts(upstream_version)
    # files: List[Tuple[str, str]] = []
    # for asset in assets:
    #    if "Star64_noble" in asset.name and asset.name[-1] == "z":
    #        files.append((asset.name, asset.browser_download_url))

    # assert len(files) == 1
    # new_toml["blob"]["distfiles"] = [files[0][0], ]
    # new_toml["distfiles"][0]["name"] = files[0][0]
    # new_toml["distfiles"][0]["urls"] = [files[0][1], ]

    # finally, set flag to ask riko package new one
    # new_pkgs[0].set_manifest_ready()
