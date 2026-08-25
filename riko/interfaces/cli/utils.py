import os


def ensure_dir(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)
