"""把研究示例展开成可独立运行的纯 PP3 文件。"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.core import compile_program
from lab.programs import PROGRAMS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", choices=["all", *PROGRAMS])
    args = parser.parse_args()
    names = PROGRAMS if args.name == "all" else [args.name]
    for name in names:
        target = Path(__file__).resolve().parents[1] / "examples" / f"{name}.pp3"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(compile_program(PROGRAMS[name]), encoding="ascii")
        print(target.name)


if __name__ == "__main__":
    main()
