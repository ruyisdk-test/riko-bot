# riko/config/config.py - 全局配置选项
"""
定义项目的全局配置常量
类似于 Java 的 application.properties 或配置类
"""

# ========== 数据目录配置 ==========
use_base_dir = True
"""
是否使用项目根目录下的 cache/ 目录
- True: 使用项目根目录/cache/（便于开发调试）
- False: 使用用户主目录/.cache/riko/（符合 XDG 规范）

类似于 Java 的配置文件中设置:
cache.dir=${project.dir}/cache 或 cache.dir=${user.home}/.cache/riko
"""

# ========== 仓库镜像配置 ==========
use_ruyi_iscas_repo = True
"""
是否使用中科院镜像源
- True: 使用 https://mirror.iscas.ac.cn/git/ruyisdk/packages-index.git
  （中国大陆用户推荐，访问速度更快）
- False: 使用官方源

类似于 Maven 的 settings.xml 中配置镜像源
"""
