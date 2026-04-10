from typing import List, Dict

from riko.core.models import RikoPkg


def rikoring(old_pkgs: List[RikoPkg], new_pkgs: List[RikoPkg]) -> None:
    """
    Process Armbian Muse Pi Pro board images
    """
    for i, new_pkg in enumerate(new_pkgs):
        new_toml: Dict = new_pkg.get_manifest()[0]
        upstream_version: str = new_pkg.get_upstream_version().replace("-trunk", "")

        # Parse version
        parts = upstream_version.split('.')
        if len(parts) >= 3:
            major, minor, patch = parts[0], parts[1], parts[2]
            new_pkgs[i].version = new_pkgs[i].version.replace(
                major=major, minor=minor, patch=patch)

        # Update metadata.desc
        old_version = old_pkgs[i].get_upstream_version() if i < len(old_pkgs) else upstream_version
        new_toml["metadata"]["desc"] = (
            new_toml["metadata"]["desc"].replace(old_version, upstream_version))
