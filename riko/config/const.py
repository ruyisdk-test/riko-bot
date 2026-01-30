# riko/config/const.py - 配置常量定义
"""
定义项目中所有使用的路径常量
类似于 Java 的 application.properties 或常量类（Constants class）
"""

from pathlib import Path  # Path 对象提供面向路径的操作（类似于 Java 的 Path 类）

# 导入配置选项
from .config import use_base_dir, use_ruyi_iscas_repo

# ========== 项目根目录 ==========
# Python 特殊语法：__file__ 表示当前文件的路径
# Path(__file__).resolve() 获取文件的绝对路径（类似于 Java 的 Paths.get().toAbsolutePath()）
# .parent.parent.parent 向上回溯 3 级目录
basedir = Path(__file__).resolve().parent.parent.parent
"""
项目根目录（riko-packaging/）
"""

# ========== 数据根目录 ==========
# Python 三元表达式：值1 if 条件 else 值2（类似于 Java 的 condition ? value1 : value2）
# 如果 use_base_dir=True，使用项目下的 cache/ 目录
# 否则使用用户主目录下的 .cache/riko/
datadir = basedir / 'cache' if use_base_dir else Path('~/.cache/riko/').expanduser()
"""
数据或缓存文件的根目录
.expanduser() 展开波浪号 ~ 为用户主目录（例如 /home/user）
"""

# ========== nvchecker 相关路径 ==========
nvchecker_datadir = datadir / 'nvchecker'  # nvchecker 数据目录
nvchecker_config = nvchecker_datadir / "nvchecker.toml"    # nvchecker 配置文件
nvchecker_result = nvchecker_datadir / "result.json"       # nvchecker 检查结果
nvchecker_old_ver = nvchecker_datadir / "old_ver.json"     # nvchecker 旧版本记录
nvchecker_new_ver = nvchecker_datadir / "new_ver.json"     # nvchecker 新版本记录
nvchecker_key = basedir / "config" / "nvchecker_keyfile.toml"  # nvchecker 密钥文件
"""
nvchecker 工具相关的所有文件路径
"""

# ========== ruyi 相关路径 ==========
ruyi_datadir = datadir / 'ruyi'  # ruyi 数据根目录
"""
ruyi 工具相关的所有文件
"""

# XDG 目录规范（Linux 桌面标准）
ruyi_config_dir = ruyi_datadir / 'config'  # 配置文件目录（XDG_CONFIG_HOME）
ruyi_data_dir = ruyi_datadir / 'local'    # 数据文件目录（XDG_DATA_HOME）
ruyi_cache_dir = ruyi_datadir / 'cache'   # 缓存文件目录（XDG_CACHE_HOME）
ruyi_state_dir = ruyi_datadir / 'state'   # 状态文件目录（XDG_STATE_HOME）

# ========== ruyi_packages 目录 ==========
ruyi_pkgs_dir = basedir / "ruyi_packages"
"""
上游包配置目录
包含各个 board-image/OS 的 riko.toml、riko.yaml、riko.py 等配置文件
"""

# ========== riko 相关路径 ==========
riko_datadir = datadir / 'riko'          # riko 数据根目录
riko_cache_dir = riko_datadir / 'cache' # riko 缓存目录
riko_manifests_dir = riko_datadir / 'manifests'  # riko 生成的清单目录
"""
riko 工具相关的所有文件
"""

# ========== ruyi 配置内容 ==========
# Python 多行字符串（使用三引号）
ruyi_config = '''
[telemetry]
mode = "local"
'''
"""
ruyi 的基础配置（TOML 格式）
设置遥测模式为本地（不发送数据到远程）
"""

# ruyi 额外配置（可选）
# 根据配置决定是否使用中科院的镜像源
ruyi_config_extra = '''
[repo]
remote = "https://mirror.iscas.ac.cn/git/ruyisdk/packages-index.git"
''' if use_ruyi_iscas_repo else ""
"""
ruyi 的额外配置
如果 use_ruyi_iscas_repo=True，添加中科院镜像源配置
"""
