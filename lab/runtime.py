"""只加载固定的原版运行器；不替换内存、指令或标准输入操作。"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "vendor" / "PP3"
if not (UPSTREAM / "src" / "pp3.py").is_file():
    raise RuntimeError("请先运行 git submodule update --init --recursive")
sys.path.insert(0, str(UPSTREAM))
from src.pp3 import Data, HandlerType, IRBuilder, Runtime, std_register


def build(code):
    ir = IRBuilder(op_map=std_register).build(code)
    allowed = {Data, *std_register.values()}

    def verify(nodes):
        for node in nodes:
            if node.TYPE == HandlerType.Mem:
                raise ValueError("实验禁止直接寻址")
            if node.TYPE == HandlerType.Loop:
                verify(node.body)
            elif node.TYPE == HandlerType.InPlace and type(node) not in allowed:
                raise ValueError("实验只允许标准注册的操作")

    verify(ir)
    return ir
