# riko/config/const.py - 配置常量定义

from pathlib import Path

# 导入配置选项
from .config import use_base_dir

from .settings import settings

basedir = Path(__file__).resolve().parent.parent.parent

datadir = settings.cache_dir or (basedir / 'cache')

nvchecker_datadir = datadir / 'nvchecker'
nvchecker_config = nvchecker_datadir / "nvchecker.toml"
nvchecker_result = nvchecker_datadir / "result.json"
nvchecker_old_ver = nvchecker_datadir / "old_ver.json"
nvchecker_new_ver = nvchecker_datadir / "new_ver.json"
nvchecker_key = basedir / "config" / "nvchecker_keyfile.toml"

ruyi_datadir = datadir / (settings.ruyi_dir or 'ruyi')

ruyi_config_dir = ruyi_datadir / 'config'
ruyi_data_dir = ruyi_datadir / 'local'
ruyi_cache_dir = ruyi_datadir / 'cache'
ruyi_state_dir = ruyi_datadir / 'state'

ruyi_pkgs_dir = basedir / "ruyi_packages"

riko_datadir = datadir / (settings.riko_dir or 'riko')
riko_cache_dir = riko_datadir / 'cache'
riko_manifests_dir = riko_datadir / 'manifests'

ruyi_config = '''
[telemetry]
mode = "local"
'''

ruyi_config_extra = '''
[repo]
remote = "https://mirror.iscas.ac.cn/git/ruyisdk/packages-index.git"
''' if settings.use_ruyi_iscas_mirror else ""
