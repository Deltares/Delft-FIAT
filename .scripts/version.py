import json
import sys
from pathlib import Path

CUR_DIR = Path(__file__).parent


def main():
    with open(
        Path(CUR_DIR, "..", "versions.json"),
        "r",
    ) as _r:
        v = json.load(_r)
    
    dirs = []
    for item in Path(CUR_DIR, "..").iterdir():
        if item.is_dir() and not item.name.startswith("."):
            dirs.append(item.name)
    
    for nw in ["stable", "latest", "dev"]:
        dirs.remove(nw)

    print(dirs)


if __name__ == "__main__":
    main()   
