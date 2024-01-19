import json
import os
import sys
from packaging import version
from pathlib import Path

BASE_URL = "https://deltares.github.io/Delft-FIAT"
CUR_DIR = Path(__file__).parent


def check():
    """_summary_"""
    with open(
        Path(CUR_DIR, "..", "versions.json"),
        "r",
    ) as _r:
        v = json.load(_r)

    vn = [item["name"] for item in v]
    vv = [version.parse(item["version"]) for item in v]
    
    dirs = []
    for item in Path(CUR_DIR, "..").iterdir():
        if item.is_dir() and not item.name.startswith("."):
            try:
                valid = version.parse(item.name)
                dirs.append(valid)
            except Exception:
                pass

    vw = []

    if sorted(dirs) != sorted(vv):
        for item in [_i for _i in dirs if _i not in vv]:
            vw.append(
                {
                    "name": f"v{item.public}",
                    "version": item.public,
                },
            )
        
        v += vw
        with open(
            Path(CUR_DIR, "..", "versions.json"),
            "w",
        ) as _w:
            json.dump(v, _w, indent=4)
        
        return dirs
    

def add(
    new: tuple | list,
):
    """_summary_"""
    with open(Path(CUR_DIR, "..", "switcher.json"),
        "r",
    ) as _r:
        s = json.load(_r)

    sv = [item["version"] for item in s]

    for nw in ["stable", "latest", "dev"]:
        if nw in sv:
            sv.remove(nw)
    sv = [version.parse(item) for item in sv]

    sw = []

    if sorted(new) != sorted(sv):
        for item in new[:-1]:
            if item not in sv:
                sw.append(
                    {
                        "name": f"v{item.public}",
                        "version": item.public,
                        "href": f"{BASE_URL}/v{item.public}/"
                    },
                )

    if len(sw) != 0:
        s += sw
        with open(Path(CUR_DIR, "..", "switcher.json"),
            "w",
        ) as _w:
            json.dump(s, _w, indent=4)

        return f"v{new[-1].public}"


if __name__ == "__main__":
    res = check()
    if check is None:
        sys.exit(1)

    res2 = add(res)
    if res2 is None:
        sys.exit(1)

    with open(os.environ['GITHUB_OUTPUT'], 'a') as fh:
        print(f'output_name={res2}', file=fh)
    
    
