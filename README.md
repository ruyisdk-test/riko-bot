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

## Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [CLI Commands](#cli-commands)
  - [FastAPI Server](#fastapi-server)
- [Dependencies](#dependencies)
- [Development](#development)
- [License](#license)

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

# Or using pip
pip install -e .

# Optional: Install API server dependencies
poetry install --extras api
# or
pip install -e ".[api]"
```

### Verify Installation

```bash
python3 -m riko --help
```

## Configuration

Riko supports multiple configuration methods with the following priority (highest to lowest):

1. **Environment Variables** (highest priority)
2. **Configuration File** (`config/config.toml`)
3. **Default Values** (in code)

### Configuration File

Copy the example configuration file and customize it:

```bash
cp config/config.toml.default config/config.toml
```

Example `config/config.toml`:

```toml
[app]
name = "riko"
version = "0.1.0"
debug = false
environment = "development"

[github]
token = "your_github_token_here"
repo_owner = "your_username"
repo_name = "packages-index"
base_branch = "pr"

[database]
url = "sqlite:///cache/riko/riko.db"
echo = false

[nvchecker]
keyfile = "nvchecker_keyfile.toml"
concurrency = 20
max_fails = 3
```

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

# Database
DATABASE_URL=sqlite:///cache/riko/riko.db

# Application
RIKO_ENV=development
RIKO_DEBUG=false
```

See [`.env.example`](.env.example) for all available options.

## Usage

### CLI Commands

Riko provides several commands for version checking, manifest generation, and PR automation.

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
INFO:riko.cli.check:run `ruyi update`
INFO:riko.cli.check:prepare for `nvchecker`
INFO:riko.cli.check:run `nvchecker`
[I 02-01 16:36:44.039 core:416] ubuntu-cdimage: updated from 25.04 to 26.04
[I 02-01 16:36:44.055 core:416] openwrt-sifiveu: updated from 24.10.4 to 24.10.5
INFO:riko.cli.check:[DB] Recorded 17 package checks (4 updated)
INFO:riko.cli.check:Check completed successfully
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
# Using uvicorn directly
uvicorn riko.app:app --reload --host 0.0.0.0 --port 8000

# Or using Python module
python3 -m uvicorn riko.app:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

#### API Documentation

Once the server is running, access:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

#### API Endpoints

##### GET /check

Trigger version check and return results:

```bash
curl http://localhost:8000/check
```

**Response:**
```json
{
  "total": 17,
  "updated": 4,
  "up_to_date": 13,
  "errors": 0,
  "packages": [
    {
      "name": "ubuntu-cdimage",
      "old_version": "25.04",
      "new_version": "26.04",
      "status": "updated"
    }
  ]
}
```

##### POST /manifests/{package_name}

Generate manifests for a package:

```bash
curl -X POST "http://localhost:8000/manifests/LicheeRV-Nano-Build" \
  -H "Content-Type: application/json" \
  -d '{
    "versions": ["20260114"],
    "down_grade": false
  }'
```

**Response:**
```json
{
  "package_name": "LicheeRV-Nano-Build",
  "combo_name": "licheerv-nano-build",
  "version": "20260114",
  "status": "success",
  "manifest_path": "/path/to/manifest.toml"
}
```

##### POST /pr/{package_name}

Create a pull request:

```bash
curl -X POST "http://localhost:8000/pr/LicheeRV-Nano-Build" \
  -H "Content-Type: application/json" \
  -d '{
    "branch_prefix": "manifest-update",
    "base_branch": "pr"
  }'
```

**Response:**
```json
{
  "package_name": "LicheeRV-Nano-Build",
  "status": "success",
  "pr_number": 123,
  "pr_url": "https://github.com/ruyisdk/packages-index/pull/123"
}
```

##### POST /scheduler/start

Start the automated scheduler:

```bash
curl -X POST "http://localhost:8000/scheduler/start" \
  -H "Content-Type: application/json" \
  -d '{
    "hour": 2,
    "minute": 0
  }'
```

##### POST /scheduler/stop

Stop the scheduler:

```bash
curl -X POST "http://localhost:8000/scheduler/stop"
```

##### GET /scheduler/status

Get scheduler status:

```bash
curl http://localhost:8000/scheduler/status
```

**Response:**
```json
{
  "running": true,
  "next_run": "2026-02-02T02:00:00",
  "last_check": "2026-02-01T02:00:00"
}
```

##### POST /scheduler/trigger

Manually trigger the daily check and PR task:

```bash
curl -X POST "http://localhost:8000/scheduler/trigger"
```

#### Python Client Example

```python
import requests

# Base URL
base_url = "http://localhost:8000"

# Check for updates
response = requests.get(f"{base_url}/check")
print(response.json())

# Generate manifests
response = requests.post(
    f"{base_url}/manifests/LicheeRV-Nano-Build",
    json={"versions": ["20260114"]}
)
print(response.json())

# Create PR
response = requests.post(
    f"{base_url}/pr/LicheeRV-Nano-Build"
)
print(response.json())
```

## Dependencies

### Python Dependencies

See [`pyproject.toml`](pyproject.toml) for the complete list:

**Core dependencies:**
- `PyGithub` - GitHub API client
- `GitPython` - Git operations
- `semver` - Semantic versioning
- `PyYAML` - YAML parsing
- `tomli` / `tomli-w` - TOML parsing
- `apscheduler` - Task scheduling
- `SQLAlchemy` - Database ORM
- `python-dotenv` - Environment variable management

**Optional (API server):**
- `fastapi` - Web framework
- `uvicorn` - ASGI server

### External Tools

- **nvchecker** - New version checker
  ```bash
  pip install nvchecker
  ```

- **ruyi** - Ruyi SDK package manager
  ```bash
  # Follow installation instructions at:
  # https://github.com/ruyisdk/ruyi
  ```

- **Git** - Version control system
  ```bash
  # Ubuntu/Debian
  sudo apt-get install git

  # Fedora/RHEL
  sudo dnf install git

  # macOS
  brew install git
  ```

## Development

### Project Structure

```
riko-packaging/
├── riko/
│   ├── __main__.py          # CLI entry point
│   ├── app.py               # FastAPI application
│   ├── api.py               # Core API models
│   ├── cli/                 # CLI commands
│   │   ├── check.py
│   │   ├── list.py
│   │   ├── manifests.py
│   │   └── pr.py
│   ├── config/              # Configuration management
│   │   ├── settings.py      # Unified settings
│   │   └── const.py         # Constants
│   ├── database/            # Database layer
│   │   ├── models.py        # SQLAlchemy models
│   │   ├── db_manager.py    # Database manager
│   │   └── recorder.py      # Command recorder
│   ├── scheduler.py         # Task scheduler
│   └── ...
├── config/
│   └── config.toml.default  # Configuration template
├── .env.example             # Environment variables template
├── pyproject.toml           # Project configuration
└── README.md                # This file
```

### Database

The project uses SQLAlchemy for database management. By default, it stores data in:
- SQLite: `cache/riko/riko.db`

Database tables:
- `scan_records` - Scan history
- `package_updates` - Version update records
- `manifest_records` - Manifest generation records
- `pr_records` - Pull request records


## License

MIT License - see [LICENSE](LICENSE) file for details

