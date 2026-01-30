#!/usr/bin/env python3
"""
Riko - Ruyi 包装机器人 CLI 入口点
类似于 Java 的 Main 类，作为程序的启动入口
"""

import argparse  # 命令行参数解析器（类似 Java 的 Apache Commons CLI）
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

    # ========== 初始化 Riko 单例 ==========
    # 使用单例模式（类似于 Java 的 Singleton Pattern）
    myriko = get_riko()

    # 从本地缓存加载数据
    # riko 不追踪 ruyi/nvchecker 的执行历史，只读取结果缓存
    myriko.load_from_cache()

    # ========== 命令行参数解析器配置 ==========
    # argparse 类似于 Java 的 JCommander 或 Apache Commons CLI
    parser = argparse.ArgumentParser(prog="riko", description="Riko: the Ruyi Packaging Bot")

    # 添加子命令支持（类似于 git 的 git add、git commit）
    # dest: 将解析结果存储到 args.subcommand 变量
    subparsers = parser.add_subparsers(dest="subcommand", help="sub-commands")

    # ========== 子命令 1: check ==========
    subparser = subparsers.add_parser("check", help="获取数据并刷新本地缓存")
    # Python 特殊语法：lambda 匿名函数（类似于 Java 的 Lambda 表达式）
    # lambda args: check()  接收 args 参数但不使用，直接调用 check()
    subparser.set_defaults(func=lambda args: check())

    # ========== 子命令 2: list ==========
    subparser = subparsers.add_parser("list", help="列出 nvchecker 结果事件或级别")
    # nargs="?" 表示可选参数（类似于 Java 的 @Option(required=false)）
    # default 设置默认值
    # choices 限制可选择的值
    subparser.add_argument(
        "event",
        help="event or level, default `updated`",
        default="updated",
        nargs="?",
        choices=["any", "updated", "up-to-date", "no-result", "debug", "info", "error"]
    )
    # lambda args: list_result(args.event) 调用函数并传递参数
    subparser.set_defaults(func=lambda args: list_result(args.event))

    # ========== 子命令 3: manifests ==========
    subparser = subparsers.add_parser("manifests", help="从旧的生成新的软件包索引清单")
    # action="store_true" 表示这是布尔标志（类似于 Java 的 boolean flag）
    # -d 和 --down-grade 都是这个参数的写法
    subparser.add_argument("-d", "--down-grade", action="store_true", help="allow generating downgrade manifests")
    # type=str 显式指定类型
    subparser.add_argument("up_name", type=str, help="upstream name")
    # nargs="*" 表示可接收任意个参数（类似于 Java 的 String... args）
    subparser.add_argument("gen_vers", nargs="*", help="specify new versions, or use nvchecker result")
    subparser.set_defaults(func=lambda args: manifests(args.up_name, args.gen_vers, args.down_grade))

    # ========== 子命令 4: pr ==========
    subparser = subparsers.add_parser("pr", help="提交 PR 到 packages-index 仓库")
    subparser.add_argument("package_name", type=str, help="上游包名称（例如：LicheeRV-Nano-Build）")
    subparser.add_argument("--branch-prefix", type=str, default="manifest-update", help="功能分支前缀（默认: manifest-update）")
    subparser.add_argument("--github-token", type=str, help="GitHub Personal Access Token（优先级: CLI > 配置文件 > 环境变量）")
    subparser.add_argument("--repo-owner", type=str, default="SmulllLu", help="GitHub 仓库所有者（默认: SmulllLu）")
    subparser.add_argument("--repo-name", type=str, default="packages-index", help="GitHub 仓库名称（默认: packages-index）")
    subparser.add_argument("--base-branch", type=str, default="pr", help="PR 目标分支（默认: pr）")
    subparser.set_defaults(func=lambda args: pr(args))

    # ========== 子命令 5: scheduler（调度器） ==========
    scheduler_parser = subparsers.add_parser("scheduler", help="定时任务调度器管理")
    scheduler_subparsers = scheduler_parser.add_subparsers(dest="scheduler_action", help="scheduler actions")

    # scheduler start - 启动调度器并保持运行
    start_parser = scheduler_subparsers.add_parser("start", help="启动定时任务调度器并保持运行")
    start_parser.add_argument("--hour", type=int, default=2, help="每天执行的小时（0-23，默认凌晨 2 点）")
    start_parser.add_argument("--minute", type=int, default=0, help="每天执行的分钟（0-59，默认 0 分）")
    start_parser.set_defaults(func=lambda args: run_scheduler_daemon(args.hour, args.minute))
    # scheduler stop - 停止调度器
    stop_parser = scheduler_subparsers.add_parser("stop", help="停止定时任务调度器")
    stop_parser.set_defaults(func=lambda args: stop_scheduler())
    # scheduler status - 查看调度器状态
    status_parser = scheduler_subparsers.add_parser("status", help="查看调度器状态")
    status_parser.set_defaults(func=lambda args: print(scheduler_status()))
    # scheduler trigger - 手动触发任务
    trigger_parser = scheduler_subparsers.add_parser("trigger", help="手动触发每日检查和 PR 任务")
    trigger_parser.set_defaults(func=lambda args: cmd_scheduler_trigger())

    # ========== 执行命令 ==========
    # sys.argv 包含命令行参数列表（类似于 Java 的 String[] args）
    # 如果没有参数，显示帮助信息
    if len(sys.argv) == 1:
        parser.print_help()
    else:
        # parse_args() 解析命令行参数并返回 Namespace 对象（类似于 Java 的 Bean）
        myfunc = parser.parse_args()
        # 调用对应的函数（根据 set_defaults 设置的 func）
        myfunc.func(myfunc)
