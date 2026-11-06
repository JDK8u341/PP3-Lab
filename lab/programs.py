"""各个研究发现的纯 PP3 示例；不包含输入值域查表。"""

from lab.core import Tape, seq
from lab.links import PROGRAMS as LINK_PROGRAMS


def graph_write(m):
    key, value, result = (m.slot(name) for name in ("键", "数值", "成员"))
    return seq(m.put(key, "@input"), m.set_add(key), m.put(value, "@input"),
               m.change(value, "@+"), m.change(value, "@-"), m.read(value) + " @print",
               m.set_contains(key, result), m.read(result) + " @print")


def equality(m):
    a, b, result = (m.slot(name) for name in ("A", "B", "相等"))
    return seq(m.put(a, "@input"), m.put(b, "@input"), m.equal(a, b, result), m.read(result) + " @print")


def sparse_set(m):
    count, key, result = (m.slot(name) for name in ("操作数", "键", "存在"))
    load = seq(m.put(key, "@input"), m.set_add(key), m.change(count, "@-"))
    query = seq(m.put(key, "@input"), m.set_contains(key, result), m.read(result) + " @print", m.change(count, "@-"))
    return seq(m.put(count, "@input"), m.loop(m.read(count), load), m.put(count, "@input"), m.loop(m.read(count), query))


def comparison(m):
    a, b, lt, eq, gt = (m.slot(name) for name in ("A", "B", "小于", "等于", "大于"))
    return seq(m.put(a, "@input"), m.put(b, "@input"), m.compare(a, b, lt, eq, gt),
               m.read(lt) + " @print", m.read(eq) + " @print", m.read(gt) + " @print")


def signed_comparison(m):
    sa, a, sb, b, lt, eq, gt = (m.slot(name) for name in ("符号A", "幅值A", "符号B", "幅值B", "小于", "等于", "大于"))
    return seq(*(m.put(slot, "@input") for slot in (sa, a, sb, b)),
               m.compare_signed(sa, a, sb, b, lt, eq, gt),
               m.read(lt) + " @print", m.read(eq) + " @print", m.read(gt) + " @print")


def comparison_sort(m):
    left, right = Tape(m, "左游标"), Tape(m, "右游标")
    n, count, outer, inner, a, b, lt, eq, gt = (m.slot(name) for name in (
        "长度", "读取剩余", "轮数", "比较剩余", "左值", "右值", "小于", "等于", "大于",
    ))
    load = seq(left.put("@input"), left.move(), m.change(count, "@-"))
    compare_step = seq(
        m.put(a, left.read()), m.put(b, right.read()), m.compare(a, b, lt, eq, gt),
        m.once(m.read(gt), seq(left.put(m.read(b)), right.put(m.read(a)))),
        left.move(), right.move(), m.change(inner, "@-"),
    )
    one_pass = seq(
        left.reset(), right.reset(), right.move(), m.copy(inner, outer), m.change(inner, "@-"),
        m.loop(m.read(inner), compare_step), m.change(outer, "@-"),
    )
    output = seq(left.read() + " @print", left.move(), m.change(count, "@-"))
    return seq(
        m.put(n, "@input"), m.copy(count, n), left.reset(), m.loop(m.read(count), load),
        m.copy(outer, n), m.loop(m.read(outer), one_pass),
        left.reset(), m.copy(count, n), m.loop(m.read(count), output),
    )


def binary_add(m):
    a, b = Tape(m, "二进制A", lane=0), Tape(m, "二进制B", lane=1)
    width, count, bit_a, bit_b, carry, partial, result, next_carry = (m.slot(name) for name in (
        "位宽", "剩余位", "位A", "位B", "进位", "半加器", "和位", "新进位",
    ))
    ab, cp = m.slot("同时为一"), m.slot("进位传播")

    def load(tape):
        # 定义域为恰好 width 个 0/1 字符及 LF；此处不增加错误处理语义
        return seq(tape.reset(), m.copy(count, width), m.loop(m.read(count), seq(
            tape.put("@input_as_char " + "@- " * 48), tape.move(), m.change(count, "@-"),
        )), "@input_as_char")

    full_adder = seq(
        a.move(forward=False), b.move(forward=False),
        m.put(bit_a, a.read()), m.put(bit_b, b.read()),
        m.xor(bit_a, bit_b, partial), m.xor(partial, carry, result),
        m.conjunction(bit_a, bit_b, ab), m.conjunction(carry, partial, cp),
        m.copy(next_carry, ab), m.once(m.read(cp), m.const(next_carry, 1)),
        a.put(m.read(result)), m.copy(carry, next_carry), m.change(count, "@-"),
    )
    return seq(
        m.put(width, "@input"), load(a), load(b), m.copy(count, width),
        m.loop(m.read(count), full_adder), m.read(carry) + " " + "@+ " * 48 + "@print_as_char",
        a.reset(), m.copy(count, width), m.loop(m.read(count), seq(
            a.read() + " " + "@+ " * 48 + "@print_as_char", a.move(), m.change(count, "@-"),
        )), "&10 @print_as_char",
    )


PROGRAMS = {
    "graph-write": graph_write,
    "equality": equality,
    "sparse-set": sparse_set,
    "comparison": comparison,
    "signed-comparison": signed_comparison,
    "comparison-sort": comparison_sort,
    "binary-add": binary_add,
    **LINK_PROGRAMS,
}
