"""测量原值链追加、记录链追加/拼接的 Runtime handler 分派数。"""

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.core import Model, seq
from lab.links import RecordHeap, RecordList, read_encoded_list
from lab.measure import dispatch_count
from lab.runtime import ROOT, Runtime, build


def encode(values):
    return str(len(values)) + "\n" + "".join(f"{int(value < 0)}\n{abs(value)}\n" for value in values)


def prepare(ir, stdin):
    runtime = Runtime(can_direct_addressing=False)
    with patch("sys.stdin", StringIO(stdin)), redirect_stdout(StringIO()):
        runtime.run(ir)
    return runtime


def main():
    sizes = [1, 8, 64, 256]
    value_chain_counts = []
    record_append_counts = []
    record_splice_counts = []

    for size in sizes:
        values = list(range(1000, 1000 + size))
        runtime = prepare(
            build("&-1 ^2 @input [ ^3 ^2 @input ]"),
            "\n".join(map(str, values + [0])) + "\n",
        )
        value_chain_counts.append(dispatch_count(build("@input ^3 ^2"), "3000\n", runtime=runtime))

        model = Model(array_base=-2000)
        heap = RecordHeap(model)
        first, second = RecordList(heap, "甲"), RecordList(heap, "乙")
        node, magnitude, sign = (model.slot(name) for name in ("新节点", "新幅值", "新符号"))
        setup = seq(
            heap.initialize(),
            read_encoded_list(model, heap, first),
            read_encoded_list(model, heap, second),
            model.const(magnitude, 3000),
            model.const(sign, 0),
            heap.allocate(node, magnitude, sign),
        )
        values = list(range(size))
        runtime = prepare(build(setup), encode(values) + encode(values))
        append = first.append(node)
        splice = first.concat(second)
        record_append_counts.append(
            dispatch_count(build(append), "", runtime=runtime)
        )
        record_splice_counts.append(
            dispatch_count(build(splice), "", runtime=runtime)
        )

    result = {
        "metric": "原版 Runtime.run 每次 handler 分派位置的命中次数；并非 CPU 指令数或真实耗时",
        "record_layout": "每节点跨度4；测试使用 -2000 起始的数据区，与普通槽隔离",
        "list_sizes": sizes,
        "value_chain_append_with_input": value_chain_counts,
        "record_tail_append": record_append_counts,
        "record_concat_ownership_transfer": record_splice_counts,
        "notes": "计数对象是孤立的追加/拼接操作，不含列表构造。空记录队列追加走不同分支，故不与非空追加合并比较。宿主字典、大整数与分支成本不由该计数表示。",
    }
    target = ROOT / "results" / "link-dispatch-counts.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
