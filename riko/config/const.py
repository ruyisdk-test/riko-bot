# riko/config/const.py - 配置常量定义

from pathlib import Path

from .settings import settings

basedir = Path(__file__).resolve().parent.parent.parent

datadir = settings.cache_dir or (basedir / 'cache')
if not datadir.is_absolute():
    # cache_dir 可能配置为相对路径（如 config.toml 里的 "./cache"），
    # 基于项目根目录解析为绝对路径。ruyi 的 [repo] local 要求绝对路径，
    # 相对路径会被 ruyi 忽略。
    datadir = basedir / datadir

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

# packages-index 仓库由 `ruyi update` clone 到 check 沙箱内固定的路径。
# 该路径通过沙箱配置里的 [repo] local 显式固定，与 ruyi 内部布局
# （新版为 $XDG_CACHE_HOME/ruyi/repos/<id>）解耦，避免 ruyi 升级改布局后失效。
ruyi_packages_index_dir = ruyi_datadir / "packages-index"

ruyi_pkgs_dir = basedir / "ruyi_packages"

riko_datadir = datadir / (settings.riko_dir or 'riko')
riko_cache_dir = riko_datadir / 'cache'
riko_manifests_dir = riko_datadir / 'manifests'

ruyi_config = '''
[telemetry]
mode = "local"
'''

ruyi_config_extra = f'''
[repo]
local = "{ruyi_packages_index_dir}"
remote = "https://github.com/ruyisdk/packages-index.git"
''' if not settings.use_ruyi_iscas_mirror else f'''
[repo]
local = "{ruyi_packages_index_dir}"
remote = "https://mirror.iscas.ac.cn/git/ruyisdk/packages-index.git"
'''
