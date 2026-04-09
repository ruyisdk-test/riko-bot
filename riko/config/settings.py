"""
  统一配置管理器
  支持配置文件和环境变量，环境变量优先级更高
"""
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import logging
# TOML 解析库（兼容 Python 3.11- 和 3.11+）
try:
    import tomllib  # Python 3.11+ 内置
except ImportError:
    import tomli as tomllib  # Python 3.10 及以下使用第三方库
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

@dataclass
class Settings:
    # 应用配置
    app_name: str = "riko"
    app_version: str = "0.1.0"
    app_debug: bool = False
    app_environment: str = "development"

    # 路径配置
    cache_dir: str = None
    base_dir: str = None

    # 数据目录配置
    nvchecker_dir: str = "nvchecker"
    ruyi_dir: str = "ruyi"
    riko_dir: str = "riko"

    # GitHub 配置
    github_token: str = ""
    github_repo_owner: str = "SmulllLu"
    github_repo_name: str = "packages-index"
    github_base_branch: str = "pr"
    pr_branch_prefix: str = "manifest-update"

    # 仓库 URL 配置
    packages_index_url: str = "https://mirror.iscas.ac.cn/git/ruyisdk/packages-index.git"
    use_ruyi_iscas_mirror: bool = True
    ruyi_mirror_url: str = "https://mirrors.iscas.ac.cn/git/ruyisdk/packages-index.git"

    # 数据库配置
    database_url: str = "sqlite:///cache/riko/riko.db"
    database_echo: bool = False

    # nvchecker 配置
    nvchecker_keyfile: str = "nvchecker_keyfile.toml"
    nvchecker_concurrency: int = 20
    nvchecker_max_fails: int = 3

    # 日志配置
    logging_level: str = "INFO"
    logging_file: str = ""
    logging_max_bytes: int = 10485760
    logging_backup_count: int = 5

    # 定时任务配置
    schedule_enable: bool = True
    schedule_check_interval_hours: int = 24

    # Telegram 配置
    telegram_token: str = ""
    telegram_chat_id: str = ""
    @classmethod
    def load(cls) -> 'Settings':
        """加载配置，按优先级合并"""
        # 加载默认信息
        config = cls._load_default()

        # 加载配置文件
        config_file = cls._find_config_file()
        if config_file:
            file_config = cls._load_toml(config_file)
            config = cls._merge(config, file_config)

        # 加载环境变量
        env_config = cls._load_env_vars()
        config = cls._merge(config, env_config)

        # 验证配置
        config.validate()

        # 展开路径
        config._expand_paths()
        return config

    @classmethod
    def _load_default(cls) -> 'Settings':
        """加载默认配置"""
        return cls()

    @classmethod
    def _load_toml(cls, config_file: Path) -> dict:
        """从 TOML 文件加载配置，展开嵌套的配置节"""
        try:
            with open(config_file, "rb") as f:
                config = tomllib.load(f)

            # 展开嵌套的配置节为扁平化的字典
            result = {}

            # [app] 节
            if "app" in config:
                app = config["app"]
                if "name" in app:
                    result["app_name"] = app["name"]
                if "version" in app:
                    result["app_version"] = app["version"]
                if "debug" in app:
                    result["app_debug"] = app["debug"]
                if "environment" in app:
                    result["app_environment"] = app["environment"]

            # [path] 节
            if "path" in config:
                path = config["path"]
                if "cache_dir" in path:
                    result["cache_dir"] = path["cache_dir"]
                if "base_dir" in path:
                    result["base_dir"] = path["base_dir"]

            # [data_dirs] 节
            if "data_dirs" in config:
                data_dirs = config["data_dirs"]
                if "nvchecker" in data_dirs:
                    result["nvchecker_dir"] = data_dirs["nvchecker"]
                if "ruyi" in data_dirs:
                    result["ruyi_dir"] = data_dirs["ruyi"]
                if "riko" in data_dirs:
                    result["riko_dir"] = data_dirs["riko"]

            # [repo] 节
            if "repo" in config:
                repo = config["repo"]
                if "use_ruyi_iscas_mirror" in repo:
                    result["use_ruyi_iscas_mirror"] = repo["use_ruyi_iscas_mirror"]
                if "ruyi_mirror_url" in repo:
                    result["ruyi_mirror_url"] = repo["ruyi_mirror_url"]
                if "packages_index_url" in repo:
                    result["packages_index_url"] = repo["packages_index_url"]

            # [nvchecker] 节
            if "nvchecker" in config:
                nvchecker = config["nvchecker"]
                if "keyfile" in nvchecker:
                    result["nvchecker_keyfile"] = nvchecker["keyfile"]
                if "concurrency" in nvchecker:
                    result["nvchecker_concurrency"] = nvchecker["concurrency"]
                if "max_fails" in nvchecker:
                    result["nvchecker_max_fails"] = nvchecker["max_fails"]

            # [database] 节
            if "database" in config:
                database = config["database"]
                if "url" in database:
                    result["database_url"] = database["url"]
                if "echo" in database:
                    result["database_echo"] = database["echo"]

            # [schedule] 节
            if "schedule" in config:
                schedule = config["schedule"]
                if "enable" in schedule:
                    result["schedule_enable"] = schedule["enable"]
                if "check_interval_hours" in schedule:
                    result["schedule_check_interval_hours"] = schedule["check_interval_hours"]

            # [github] 节
            if "github" in config:
                github = config["github"]
                if "token" in github:
                    result["github_token"] = github["token"]
                if "repo_owner" in github:
                    result["github_repo_owner"] = github["repo_owner"]
                if "repo_name" in github:
                    result["github_repo_name"] = github["repo_name"]
                if "base_branch" in github:
                    result["github_base_branch"] = github["base_branch"]

            # [pr] 节
            if "pr" in config:
                pr = config["pr"]
                if "branch_prefix" in pr:
                    result["pr_branch_prefix"] = pr["branch_prefix"]

            # [logging] 节
            if "logging" in config:
                logging_config = config["logging"]
                if "level" in logging_config:
                    result["logging_level"] = logging_config["level"]
                if "file" in logging_config:
                    result["logging_file"] = logging_config["file"]
                if "max_bytes" in logging_config:
                    result["logging_max_bytes"] = logging_config["max_bytes"]
                if "backup_count" in logging_config:
                    result["logging_backup_count"] = logging_config["backup_count"]

            # [telegram] 节
            if "telegram" in config:
                telegram = config["telegram"]
                if "token" in telegram:
                    result["telegram_token"] = telegram["token"]
                if "chat_id" in telegram:
                    result["telegram_chat_id"] = str(telegram["chat_id"])

            return result
        except Exception as e:
            print(f"Warning: Failed to load config file {config_file}: {e}")
            return {}

    @classmethod
    def _merge(cls, base: 'Settings', updates: dict) -> 'Settings':
        """合并配置"""
        for key, value in updates.items():
            if hasattr(base, key) and value is not None:
                setattr(base, key, value)
        return base

    @classmethod
    def _find_config_file(cls) -> Optional[Path]:
        """查找配置文件"""
        # 按优先级查找
        candidates = [
            Path("config/config.toml"),  # 项目配置
            Path.home() / ".config/riko/config.toml",  # 用户配置
        ]
        for path in candidates:
            if path.exists():
                return path
        return None

    @classmethod
    def _load_env_vars(cls) -> dict:
        """加载环境变量"""
        return {
            # 应用配置
            "app_debug": os.getenv("RIKO_DEBUG", "").lower() == "true",
            "app_environment": os.getenv("RIKO_ENV", "development"),

            # GitHub 配置
            "github_token": os.getenv("GITHUB_TOKEN", ""),
            "github_repo_owner": os.getenv("GITHUB_REPO_OWNER", ""),
            "github_repo_name": os.getenv("GITHUB_REPO_NAME", ""),
            "github_base_branch": os.getenv("GITHUB_BASE_BRANCH", ""),

            # 仓库配置
            "packages_index_url": os.getenv("PACKAGES_INDEX_URL", ""),
            "use_ruyi_iscas_mirror": os.getenv("USE_RUYI_ISCAS_MIRROR", "").lower() == "true" if os.getenv("USE_RUYI_ISCAS_MIRROR") is not None else None,

            # 数据库配置
            "database_url": os.getenv("DATABASE_URL", ""),
            "database_echo": os.getenv("DATABASE_ECHO", "").lower() == "true",

            # 日志配置
            "logging_level": os.getenv("LOGGING_LEVEL", "INFO"),
            "logging_file": os.getenv("LOGGING_FILE", ""),

            # Telegram 配置
            "telegram_token": os.getenv("TELEGRAM_TOKEN", ""),
            "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        }

    def validate(self):
        """配置验证"""
        if self.app_environment == "production" and not self.github_token:
            raise ValueError("生产环境必须配置 GITHUB_TOKEN")

        # 验证 GitHub token 格式（GitHub token 通常以特定前缀开头）
        if self.github_token:
            # 基本格式验证：GitHub token 应该至少 40 字符
            if len(self.github_token) < 20:
                raise ValueError("GitHub token 格式无效：token 长度过短")

            # 记录时屏蔽 token（仅用于调试）

            logger = logging.getLogger(__name__)
            masked_token = f"{self.github_token[:8]}...{self.github_token[-4:]}" if len(self.github_token) > 12 else "***"
            logger.debug(f"GitHub token configured: {masked_token}")

    def __str__(self):
        """安全的字符串表示，屏蔽敏感信息"""
        result = []
        for key, value in self.__dict__.items():
            if 'token' in key.lower() or 'password' in key.lower():
                if value and len(str(value)) > 12:
                    masked_value = f"{str(value)[:8]}...{str(value)[-4:]}"
                else:
                    masked_value = "***"
                result.append(f"{key}={masked_value}")
            else:
                result.append(f"{key}={value}")
        return ", ".join(result)

    def __repr__(self):
        """安全的表示形式，屏蔽敏感信息"""
        return self.__str__()

    def _expand_paths(self):
        """展开路径中的~和相对路径"""
        if self.cache_dir:
            self.cache_dir = Path(self.cache_dir).expanduser()

# 全局单例
settings = Settings.load()
