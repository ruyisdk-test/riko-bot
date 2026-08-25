#!/usr/bin/env python3

import argparse
import logging
import sys

from riko.interfaces.cli.check import check
from riko.interfaces.cli.list import list_result
from riko.interfaces.cli.manifests import manifests
from riko.interfaces.cli.pr import pr
from riko.core import get_riko
from riko.services.scheduler_service import (
    stop_scheduler,
    scheduler_status,
    cmd_scheduler_trigger,
    run_scheduler_daemon,
)
from riko.interfaces.cli.telegramBot import telegramBot
from riko.interfaces.cli.version_sync import version_sync

logging.basicConfig(level=logging.INFO)


def main():
    myriko = get_riko()
    myriko.load_from_cache()

    parser = argparse.ArgumentParser(prog="riko", description="Riko: the Ruyi Packaging Bot")

    subparsers = parser.add_subparsers(dest="subcommand", help="sub-commands")

    subparser = subparsers.add_parser("check", help="fetch data and refresh the local cache")
    subparser.set_defaults(func=lambda args: check())

    subparser = subparsers.add_parser("list", help="list nvchecker result events or levels")
    subparser.add_argument(
        "event",
        help="event or level, default `updated`",
        default="updated",
        nargs="?",
        choices=["any", "updated", "up-to-date", "no-result", "debug", "info", "error"]
    )
    subparser.set_defaults(func=lambda args: list_result(args.event))

    subparser = subparsers.add_parser("manifests", help="generate new package index manifests from old ones")
    subparser.add_argument("-d", "--down-grade", action="store_true", help="allow generating downgrade manifests")
    subparser.add_argument("up_name", type=str, help="upstream name")
    subparser.add_argument("gen_vers", nargs="*", help="specify new versions, or use nvchecker result")
    subparser.set_defaults(func=lambda args: manifests(args.up_name, args.gen_vers, args.down_grade))

    subparser = subparsers.add_parser("pr", help="submit a PR to the packages-index repo")
    subparser.add_argument("package_name", type=str, help="upstream package name (e.g. LicheeRV-Nano-Build)")
    subparser.add_argument("--branch-prefix", type=str, default="manifest-update", help="feature branch prefix (default: manifest-update)")
    subparser.add_argument("--github-token", type=str, help="GitHub Personal Access Token (priority: CLI > config file > env var)")
    subparser.add_argument("--repo-owner", type=str, default="SmulllLu", help="GitHub repo owner (default: SmulllLu)")
    subparser.add_argument("--repo-name", type=str, default="packages-index", help="GitHub repo name (default: packages-index)")
    subparser.add_argument("--base-branch", type=str, default="pr", help="PR target branch (default: pr)")
    subparser.set_defaults(func=lambda args: pr(args))

    scheduler_parser = subparsers.add_parser("scheduler", help="manage the scheduled task scheduler")
    scheduler_subparsers = scheduler_parser.add_subparsers(dest="scheduler_action", help="scheduler actions")

    start_parser = scheduler_subparsers.add_parser("start", help="start the scheduled task scheduler and keep it running")
    start_parser.add_argument("--hour", type=int, default=2, help="hour of day to run (0-23, default 2)")
    start_parser.add_argument("--minute", type=int, default=0, help="minute of hour to run (0-59, default 0)")
    start_parser.set_defaults(func=lambda args: run_scheduler_daemon(args.hour, args.minute))
    stop_parser = scheduler_subparsers.add_parser("stop", help="stop the scheduled task scheduler")
    stop_parser.set_defaults(func=lambda args: stop_scheduler())
    status_parser = scheduler_subparsers.add_parser("status", help="show scheduler status")
    status_parser.set_defaults(func=lambda args: print(scheduler_status()))
    trigger_parser = scheduler_subparsers.add_parser("trigger", help="manually trigger the daily check and PR task")
    trigger_parser.set_defaults(func=lambda args: cmd_scheduler_trigger())

    subparser = subparsers.add_parser("telegram-bot", help="start the Telegram bot")
    subparser.set_defaults(func=lambda args: telegramBot())

    subparser = subparsers.add_parser("version-sync", help="sync upstream versions with packages-index")
    subparser.add_argument("--dry-run", action="store_true", help="only show changes without performing Git operations")
    subparser.add_argument("--package", type=str, metavar="PACKAGE_NAME", help="only sync the specified package (e.g. freebsd)")
    subparser.add_argument("-v", "--verbose", action="store_true", help="show detailed version info")
    subparser.add_argument("--github-token", type=str, help="GitHub Personal Access Token (priority: CLI > config file)")
    subparser.add_argument("--repo-owner", type=str, help="GitHub repo owner (default: SmulllLu)")
    subparser.add_argument("--repo-name", type=str, help="GitHub repo name (default: packages-index)")
    subparser.add_argument("--base-branch", type=str, help="PR target branch (default: pr)")
    subparser.add_argument("--branch-prefix", type=str, help="feature branch prefix (default: manifest-update)")
    subparser.set_defaults(func=lambda args: version_sync(args))

    if len(sys.argv) == 1:
        parser.print_help()
    else:
        myfunc = parser.parse_args()
        myfunc.func(myfunc)


if __name__ == '__main__':
    main()
