"""只用 Python 行跟踪计数原版运行器的分派次数，不改动运行语义。"""

from contextlib import redirect_stdout
from io import StringIO
import inspect
import sys
from unittest.mock import patch

from lab.runtime import Runtime


def dispatch_count(ir, stdin, runtime=None):
    lines, start = inspect.getsourcelines(Runtime.run)
    dispatch_line = start + next(index for index, line in enumerate(lines) if line.strip() == "if h.TYPE == HandlerType.Mem:")
    count = 0
    code = Runtime.run.__code__

    def trace(frame, event, arg):
        nonlocal count
        if frame.f_code is not code:
            return None
        if event == "line" and frame.f_lineno == dispatch_line:
            count += 1
        return trace

    previous = sys.gettrace()
    try:
        with patch("sys.stdin", StringIO(stdin)), redirect_stdout(StringIO()):
            sys.settrace(trace)
            rt = runtime if runtime is not None else Runtime(can_direct_addressing=False)
            rt.run(ir)
    finally:
        sys.settrace(previous)
    return count
