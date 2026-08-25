from typing import ClassVar, Protocol


class Upstream(Protocol):
    source: ClassVar[str]
