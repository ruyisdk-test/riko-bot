from pathlib import Path

from .settings import settings

basedir = Path(__file__).resolve().parent.parent.parent

datadir = settings.cache_dir or (basedir / 'cache')
if not datadir.is_absolute():
    # ruyi [repo] local requires an absolute path
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

# packages-index is cloned here by `ruyi update`, decoupled from ruyi's internal repo layout
ruyi_packages_index_dir = ruyi_datadir / "packages-index"

ruyi_pkgs_dir = basedir / "ruyi_packages"

# output dir for version-sync --dry-run logs and Markdown reports
dry_run_docs_dir = basedir / "version-dry-run_docs"

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
