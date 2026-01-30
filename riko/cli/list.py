# riko/cli/list.py - 列出 nvchecker 检查结果

import json
import sys

from typing import Dict, List

from ..rikoriko import get_riko


def list_result(event: str) -> None:
    res: List[Dict] = get_riko().get_nvchecker_results(event)
    json.dump(res, sys.stdout, indent=2, sort_keys=False)
