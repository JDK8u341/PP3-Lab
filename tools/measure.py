"""生成地址等值和位表示加法的可重复分派计数报告。"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.core import compile_program
from lab.measure import dispatch_count
from lab.programs import PROGRAMS
from lab.runtime import ROOT, build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "dispatch-counts.json")
    args = parser.parse_args()
    equality = build(compile_program(PROGRAMS["equality"]))
    adder = build(compile_program(PROGRAMS["binary-add"]))
    eq_results = []
    for digits in [1, 10, 100, 1000]:
        value = 0 if digits == 1 else 10 ** (digits - 1)
        eq_results.append({"decimal_digits": digits,
                           "equal_dispatches": dispatch_count(equality, f"{value}\n{value}\n"),
                           "unequal_dispatches": dispatch_count(equality, f"{value}\n{value + 1}\n")})
    addition_results = []
    for width in [8, 16, 32, 64, 128, 256, 512, 1024]:
        text = f"{width}\n" + "1" * width + "\n" + "0" * (width - 1) + "1\n"
        addition_results.append({"bit_width": width, "dispatches": dispatch_count(adder, text)})
    result = {
        "metric": "原版 Runtime.run 对每个 handler（包括 LoopBlock）的实际分派次数；不计循环条件求值次数及各 handler 内部成本",
        "limitations": "不是 CPU 指令、内存访问次数或真实耗时；Python 大整数、字典及输入输出成本不固定",
        "equality": eq_results, "binary_add": addition_results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
