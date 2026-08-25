import json
import os

from pathlib import Path
from typing import Dict, List


class NvcheckerResults:

    def __init__(self, path: Path):
        self._path: Path = path
        self._data: List[Dict] = []

    def load(self) -> None:
        if not os.path.exists(self._path):
            raise FileNotFoundError(self._path)

        with open(self._path) as f:
            content = f.read()
            # handle empty file (first run or no results yet)
            if not content or content.strip() == "":
                self._data = []
                return
            self._data = json.loads(content)

    def get_data(self) -> List[Dict]:
        return self._data

    def get_event_data(self, event_or_level: str) -> List[Dict]:
        res = []

        for r in self._data:
            ev = r.get("event")
            lv = r.get("level")

            if ev is not None and ev == event_or_level:
                res.append(r)
            elif lv is not None and lv == event_or_level:
                res.append(r)

        return res
