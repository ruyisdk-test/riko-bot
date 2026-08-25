import json
import sys

from typing import Dict, List

from ...core import get_riko


def list_result(event: str) -> None:
    res: List[Dict] = get_riko().get_nvchecker_results(event)
    json.dump(res, sys.stdout, indent=2, sort_keys=False)
