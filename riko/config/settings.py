from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import logging
try:
    import tomllib
except ImportError:
    import tomli as tomllib
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    app_name: str = "riko"
    app_version: str = "0.1.0"
    app_debug: bool = False
    app_environment: str = "development"

    cache_dir: str = None
    base_dir: str = None

    nvchecker_dir: str = "nvchecker"
    ruyi_dir: str = "ruyi"
    riko_dir: str = "riko"

    github_token: str = ""
    github_repo_owner: str = "SmulllLu"
    github_repo_name: str = "packages-index"
    github_base_branch: str = "pr"
    pr_branch_prefix: str = "manifest-update"

    packages_index_url: str = "https://mirror.iscas.ac.cn/git/ruyisdk/packages-index.git"
    use_ruyi_iscas_mirror: bool = True
    ruyi_mirror_url: str = "https://mirrors.iscas.ac.cn/git/ruyisdk/packages-index.git"

    database_url: str = "sqlite:///cache/riko/riko.db"
    database_echo: bool = False

    nvchecker_keyfile: str = "nvchecker_keyfile.toml"
    nvchecker_concurrency: int = 20
    nvchecker_max_fails: int = 3

    logging_level: str = "INFO"
    logging_file: str = ""
    logging_max_bytes: int = 10485760
    logging_backup_count: int = 5

    schedule_enable: bool = True
    schedule_check_interval_hours: int = 24

    telegram_token: str = ""
    telegram_chat_id: str = ""
    @classmethod
    def load(cls) -> 'Settings':
        config = cls._load_default()

        config_file = cls._find_config_file()
        if config_file:
            file_config = cls._load_toml(config_file)
            config = cls._merge(config, file_config)

        env_config = cls._load_env_vars()
        config = cls._merge(config, env_config)

        config.validate()

        config._expand_paths()
        return config

    @classmethod
    def _load_default(cls) -> 'Settings':
        return cls()

    @classmethod
    def _load_toml(cls, config_file: Path) -> dict:
        try:
            with open(config_file, "rb") as f:
                config = tomllib.load(f)

            result = {}

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

            if "path" in config:
                path = config["path"]
                if "cache_dir" in path:
                    result["cache_dir"] = path["cache_dir"]
                if "base_dir" in path:
                    result["base_dir"] = path["base_dir"]

            if "data_dirs" in config:
                data_dirs = config["data_dirs"]
                if "nvchecker" in data_dirs:
                    result["nvchecker_dir"] = data_dirs["nvchecker"]
                if "ruyi" in data_dirs:
                    result["ruyi_dir"] = data_dirs["ruyi"]
                if "riko" in data_dirs:
                    result["riko_dir"] = data_dirs["riko"]

            if "repo" in config:
                repo = config["repo"]
                if "use_ruyi_iscas_mirror" in repo:
                    result["use_ruyi_iscas_mirror"] = repo["use_ruyi_iscas_mirror"]
                if "ruyi_mirror_url" in repo:
                    result["ruyi_mirror_url"] = repo["ruyi_mirror_url"]
                if "packages_index_url" in repo:
                    result["packages_index_url"] = repo["packages_index_url"]

            if "nvchecker" in config:
                nvchecker = config["nvchecker"]
                if "keyfile" in nvchecker:
                    result["nvchecker_keyfile"] = nvchecker["keyfile"]
                if "concurrency" in nvchecker:
                    result["nvchecker_concurrency"] = nvchecker["concurrency"]
                if "max_fails" in nvchecker:
                    result["nvchecker_max_fails"] = nvchecker["max_fails"]

            if "database" in config:
                database = config["database"]
                if "url" in database:
                    result["database_url"] = database["url"]
                if "echo" in database:
                    result["database_echo"] = database["echo"]

            if "schedule" in config:
                schedule = config["schedule"]
                if "enable" in schedule:
                    result["schedule_enable"] = schedule["enable"]
                if "check_interval_hours" in schedule:
                    result["schedule_check_interval_hours"] = schedule["check_interval_hours"]

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

            if "pr" in config:
                pr = config["pr"]
                if "branch_prefix" in pr:
                    result["pr_branch_prefix"] = pr["branch_prefix"]

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
        for key, value in updates.items():
            if hasattr(base, key) and value is not None:
                setattr(base, key, value)
        return base

    @classmethod
    def _find_config_file(cls) -> Optional[Path]:
        candidates = [
            Path("config/config.toml"),
            Path.home() / ".config/riko/config.toml",
        ]
        for path in candidates:
            if path.exists():
                return path
        return None

    @classmethod
    def _load_env_vars(cls) -> dict:
        return {
            "app_debug": os.getenv("RIKO_DEBUG", "").lower() == "true",
            "app_environment": os.getenv("RIKO_ENV", "development"),

            "github_token": os.getenv("GITHUB_TOKEN", ""),
            "github_repo_owner": os.getenv("GITHUB_REPO_OWNER", ""),
            "github_repo_name": os.getenv("GITHUB_REPO_NAME", ""),
            "github_base_branch": os.getenv("GITHUB_BASE_BRANCH", ""),

            "packages_index_url": os.getenv("PACKAGES_INDEX_URL", ""),
            "use_ruyi_iscas_mirror": os.getenv("USE_RUYI_ISCAS_MIRROR", "").lower() == "true" if os.getenv("USE_RUYI_ISCAS_MIRROR") is not None else None,

            "database_url": os.getenv("DATABASE_URL", ""),
            "database_echo": os.getenv("DATABASE_ECHO", "").lower() == "true",

            "logging_level": os.getenv("LOGGING_LEVEL", "INFO"),
            "logging_file": os.getenv("LOGGING_FILE", ""),

            "telegram_token": os.getenv("TELEGRAM_TOKEN", ""),
            "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        }

    def validate(self):
        if self.app_environment == "production" and not self.github_token:
            raise ValueError("GITHUB_TOKEN is required in production")

        if self.github_token:
            if len(self.github_token) < 20:
                raise ValueError("Invalid GitHub token: token too short")

            logger = logging.getLogger(__name__)
            masked_token = f"{self.github_token[:8]}...{self.github_token[-4:]}" if len(self.github_token) > 12 else "***"
            logger.debug(f"GitHub token configured: {masked_token}")

    def __str__(self):
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
        return self.__str__()

    def _expand_paths(self):
        if self.cache_dir:
            self.cache_dir = Path(self.cache_dir).expanduser()

settings = Settings.load()
