# Ruyi Packaging Bot (Riko)

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Riko** is **r**uy**i** pac**k**aging b**o**t - an automated version checker and packaging tool for [ruyisdk/packages-index](https://github.com/ruyisdk/packages-index/).

## Features

- 🔍 **Version Checking**: Automatically check for new package versions using nvchecker
- 📦 **Manifest Generation**: Generate package manifests for different combos
- 🔀 **Pull Request Automation**: Automatically create PRs to packages-index repository
- ⏰ **Scheduled Tasks**: Built-in scheduler for daily automated checks
- 🗄️ **Database Storage**: Track scan history and package updates
- 🌐 **REST API**: Optional FastAPI server for web integration
- ⚙️ **Configuration Management**: Unified configuration via TOML files and environment variables
- 🏗️ **Three-tier Architecture**: Clean separation of concerns with core, services, and interfaces layers

## Table of Contents

- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [CLI Commands](#cli-commands)
  - [FastAPI Server](#fastapi-server)
- [Dependencies](#dependencies)
- [Development](#development)
- [License](#license)

## Architecture

Riko follows a **three-tier architecture** pattern for clean separation of concerns:

```
┌──────────────────────────────────────────────┐
│         interfaces/ (接口层)                  │
│  CLI (interfaces/cli/)  API (interfaces/api/)│
│  - User interaction                          │
│  - Request handling                          │
└──────────────────┬───────────────────────────┘
                   │ 依赖
                   ▼
┌─────────────────────────────────────────────┐
│         services/ (服务层)                   │
│  - Business logic orchestration             │
│  - Service coordination                     │
│  - Workflow management                      │
└──────────────────┬──────────────────────────┘
                   │ 依赖
                   ▼
┌─────────────────────────────────────────────┐
│          core/ (核心层)                      │
│  - Domain models                            │
│  - Business rules                           │
│  - Data access objects                      │
└──────────────────┬──────────────────────────┘
                   │ 依赖
                   ▼
┌─────────────────────────────────────────────┐
│        基础模块                              │
│  config, database, nvchecker,               │
│  packages_index, ruyi_packages, upstreams   │
└─────────────────────────────────────────────┘
```

### Layer Responsibilities

**Core Layer (`riko/core/`)**
- Defines domain models (`RikoPkg`, `GithubUpstream`, `RegexUpstream`)
- Contains the main `Riko` business class
- Manages data access and business rules
- No dependencies on services or interfaces

**Services Layer (`riko/services/`)**
- Orchestrates business workflows
- Coordinates between core components
- Implements command patterns with database recording
- Examples: `CheckService`, `ManifestService`, `PRService`, `SchedulerService`

**Interfaces Layer (`riko/interfaces/`)**
- **CLI** (`interfaces/cli/`): Command-line interface
- **API** (`interfaces/api/`): REST API with FastAPI
- Handles user input and output
- Delegates business logic to services layer

### Project Structure

```
riko-packaging/
├── riko/
│   ├── core/                      # 【核心层】业务逻辑和数据模型
│   │   ├── riko.py               # 核心业务类
│   │   └── models.py             # 数据模型
│   │
│   ├── services/                  # 【服务层】业务服务编排
│   │   ├── check_service.py       # 版本检查服务
│   │   ├── manifest_service.py    # 清单生成服务
│   │   ├── pr_service.py          # PR 创建服务
│   │   └── scheduler_service.py   # 调度器服务
│   │   └── telegramBot_service.py # Telegram 机器人服务
│   │
│   ├── interfaces/                # 【接口层】外部接口
│   │   ├── cli/                  # CLI 命令
│   │   │   ├── check.py
│   │   │   ├── list.py
│   │   │   ├── manifests.py
│   │   │   ├── pr.py
│   │   │   └── utils.py
│   │   │
│   │   └── api/                  # Web API
│   │       ├── app.py            # FastAPI 应用
│   │       ├── routes/           # 路由模块
│   │       │   ├── check_routes.py
│   │       │   ├── manifest_routes.py
│   │       │   ├── pr_routes.py
│   │       │   └── scheduler_routes.py 
│   │       │   └── telegramBot_routes.py 
│   │       └── models/
│   │           └── schemas.py     # Pydantic 模型
│   │
│   ├── config/                    # 配置模块
│   ├── database/                  # 数据库模块
│   ├── nvchecker/                 # 版本检查模块
│   ├── packages_index/            # 包索引模块
│   ├── ruyi_packages/             # Ruyi 包模块
│   ├── upstreams/                 # 上游源模块
│   ├── __init__.py
│   └── __main__.py               # CLI 入口
│
├── config/                        # 配置文件模板
├── docs/                          # 文档
│   └── refactoring_report.md    # 重构报告
├── .env.example                   # 环境变量模板
├── pyproject.toml                # 项目配置
└── README.md                     # 本文件
```

## Installation

### Prerequisites

- Python 3.10 or higher
- [nvchecker](https://github.com/lilydjwg/nvchecker)
- [ruyi](https://github.com/ruyisdk/ruyi)
- Git

### Install from Source

```bash
# Clone the repository
git clone https://github.com/ruyisdk/ruyi-packaging.git
cd ruyi-packaging

# Install dependencies using Poetry (recommended)
poetry install

# Optional: Install API server dependencies
poetry install --extras api
# or
pip install -e ".[api]"
```

### Verify Installation

```bash
# Run riko directly
python3 -m riko --help
```

## Configuration

Riko supports multiple configuration methods with the following priority (highest to lowest):

1. **Environment Variables** (highest priority)
2. **Configuration File** (`config/config.toml`)
3. **Default Values** (in code)

### Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Key environment variables:

```bash
# GitHub Configuration
GITHUB_TOKEN=your_github_token_here
GITHUB_REPO_OWNER=your_username
GITHUB_REPO_NAME=packages-index
GITHUB_BASE_BRANCH=pr

# Database
DATABASE_URL=sqlite:///cache/riko/riko.db

# Application
RIKO_ENV=development
RIKO_DEBUG=false

# Telegram Bot (optional)
TELEGRAM_TOKEN=your_bot_token

# Proxy (optional, for accessing Telegram API in mainland China)
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```

See [`.env.example`](.env.example) for all available options.

## Usage

### CLI Commands

Riko provides several commands for version checking, manifest generation, and PR automation.

#### Running Commands

```bash
# Run riko commands
python3 -m riko <command>
```

#### `riko check`

Fetch version updates and refresh local cache:

```bash
python3 -m riko check
```

This command:
1. Runs `ruyi update` to update local package index
2. Executes `nvchecker` to check for new versions
3. Records version updates to database
4. Displays packages with new versions

**Example output:**
```
INFO:riko.services.check_service:run `ruyi update`
INFO:riko.services.check_service:prepare for `nvchecker`
INFO:riko.services.check_service:run `nvchecker`
[I 02-01 16:36:44.039 core:416] ubuntu-cdimage: updated from 25.04 to 26.04
[I 02-01 16:36:44.055 core:416] openwrt-sifiveu: updated from 24.10.4 to 24.10.5
INFO:riko.services.check_service:[DB] Recorded 17 package checks (4 updated)
INFO:riko.services.check_service:Check completed successfully
```

#### `riko list`

List nvchecker results by event type:

```bash
# List updated packages (default)
python3 -m riko list updated

# List all events
python3 -m riko list any

# List by log level
python3 -m riko list error
```

**Available options:**
- `any` - All events
- `updated` - Updated packages (default)
- `up-to-date` - Packages already up to date
- `no-result` - Packages with no result
- `debug` / `info` / `error` - Log levels

#### `riko manifests`

Generate package manifests from nvchecker results:

```bash
# Generate manifests for all updated versions
python3 -m riko manifests LicheeRV-Nano-Build

# Generate specific versions
python3 -m riko manifests LicheeRV-Nano-Build 20260114 20260115

# Allow downgrade manifests
python3 -m riko manifests LicheeRV-Nano-Build -d
```

**Parameters:**
- `up_name` - Upstream package name (required)
- `gen_vers` - Specific versions to generate (optional, uses nvchecker results if not specified)
- `-d, --down-grade` - Allow generating downgrade manifests

#### `riko pr`

Create a pull request to packages-index repository:

```bash
# Basic usage
python3 -m riko pr LicheeRV-Nano-Build

# Custom options
python3 -m riko pr LicheeRV-Nano-Build \
  --branch-prefix manifest-update \
  --repo-owner your_username \
  --base-branch main
```

**Options:**
- `--branch-prefix` - Branch name prefix (default: `manifest-update`)
- `--github-token` - GitHub Personal Access Token (overrides config)
- `--repo-owner` - Repository owner (default: from config)
- `--repo-name` - Repository name (default: `packages-index`)
- `--base-branch` - Target branch for PR (default: `pr`)

This command:
1. Finds cached manifest files for the package
2. Syncs manifests to packages-index repository
3. Creates a new git branch
4. Commits changes
5. Pushes to remote
6. Creates a pull request via GitHub API

#### `riko scheduler`

Manage the automated task scheduler:

```bash
# Start scheduler (runs daily at 2:00 AM)
python3 -m riko scheduler start --hour 2 --minute 0

# Stop scheduler
python3 -m riko scheduler stop

# Check scheduler status
python3 -m riko scheduler status

# Manually trigger daily check and PR task
python3 -m riko scheduler trigger
```

**Scheduler features:**
- Automated daily version checks
- Automatic PR creation for updated packages
- Configurable execution time
- Status monitoring and manual triggering

### FastAPI Server

Riko includes an optional FastAPI server for REST API access.

#### Start the Server

```bash
# Using Python module
python3 -m uvicorn riko.interfaces.api.app:app --reload --host 127.0.0.0 --port 7777
```

The API will be available at `http://localhost:7777`



## License

MIT License - see [LICENSE](LICENSE) file for details
