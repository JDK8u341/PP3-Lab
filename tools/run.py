"""在未修改的 PP3 运行器中执行研究示例。"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.runtime import ROOT, Runtime, build
from lab.programs import PROGRAMS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", choices=PROGRAMS)
    args = parser.parse_args()
    code = (ROOT / "examples" / f"{args.name}.pp3").read_text(encoding="ascii")
    Runtime(can_direct_addressing=False).run(build(code))


if __name__ == "__main__":
    main()
