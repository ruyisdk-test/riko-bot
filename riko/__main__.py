#!/usr/bin/env python3

import argparse
import logging
import sys

# 导入各子命令的实现函数
from riko.cli.check import check
from riko.cli.list import list_result
from riko.cli.manifests import manifests
from riko.cli.pr import pr
from riko.rikoriko import get_riko
from riko.scheduler import (
    stop_scheduler,
    scheduler_status,
    cmd_scheduler_trigger,
    run_scheduler_daemon,
)

# 配置日志级别
logging.basicConfig(level=logging.INFO)


if __name__ == '__main__':

    myriko = get_riko()
    myriko.load_from_cache()

    parser = argparse.ArgumentParser(prog="riko", description="Riko: the Ruyi Packaging Bot")

    subparsers = parser.add_subparsers(dest="subcommand", help="sub-commands")

    subparser = subparsers.add_parser("check", help="获取数据并刷新本地缓存")
    subparser.set_defaults(func=lambda args: check())

    subparser = subparsers.add_parser("list", help="列出 nvchecker 结果事件或级别")
    subparser.add_argument(
        "event",
        help="event or level, default `updated`",
        default="updated",
        nargs="?",
        choices=["any", "updated", "up-to-date", "no-result", "debug", "info", "error"]
    )
    subparser.set_defaults(func=lambda args: list_result(args.event))

    subparser = subparsers.add_parser("manifests", help="从旧的生成新的软件包索引清单")
    subparser.add_argument("-d", "--down-grade", action="store_true", help="allow generating downgrade manifests")
    subparser.add_argument("up_name", type=str, help="upstream name")
    subparser.add_argument("gen_vers", nargs="*", help="specify new versions, or use nvchecker result")
    subparser.set_defaults(func=lambda args: manifests(args.up_name, args.gen_vers, args.down_grade))

    subparser = subparsers.add_parser("pr", help="提交 PR 到 packages-index 仓库")
    subparser.add_argument("package_name", type=str, help="上游包名称（例如：LicheeRV-Nano-Build）")
    subparser.add_argument("--branch-prefix", type=str, default="manifest-update", help="功能分支前缀（默认: manifest-update）")
    subparser.add_argument("--github-token", type=str, help="GitHub Personal Access Token（优先级: CLI > 配置文件 > 环境变量）")
    subparser.add_argument("--repo-owner", type=str, default="SmulllLu", help="GitHub 仓库所有者（默认: SmulllLu）")
    subparser.add_argument("--repo-name", type=str, default="packages-index", help="GitHub 仓库名称（默认: packages-index）")
    subparser.add_argument("--base-branch", type=str, default="pr", help="PR 目标分支（默认: pr）")
    subparser.set_defaults(func=lambda args: pr(args))

    scheduler_parser = subparsers.add_parser("scheduler", help="定时任务调度器管理")
    scheduler_subparsers = scheduler_parser.add_subparsers(dest="scheduler_action", help="scheduler actions")

    start_parser = scheduler_subparsers.add_parser("start", help="启动定时任务调度器并保持运行")
    start_parser.add_argument("--hour", type=int, default=2, help="每天执行的小时（0-23，默认凌晨 2 点）")
    start_parser.add_argument("--minute", type=int, default=0, help="每天执行的分钟（0-59，默认 0 分）")
    start_parser.set_defaults(func=lambda args: run_scheduler_daemon(args.hour, args.minute))
    stop_parser = scheduler_subparsers.add_parser("stop", help="停止定时任务调度器")
    stop_parser.set_defaults(func=lambda args: stop_scheduler())
    status_parser = scheduler_subparsers.add_parser("status", help="查看调度器状态")
    status_parser.set_defaults(func=lambda args: print(scheduler_status()))
    trigger_parser = scheduler_subparsers.add_parser("trigger", help="手动触发每日检查和 PR 任务")
    trigger_parser.set_defaults(func=lambda args: cmd_scheduler_trigger())

    if len(sys.argv) == 1:
        parser.print_help()
    else:
        myfunc = parser.parse_args()
        myfunc.func(myfunc)
