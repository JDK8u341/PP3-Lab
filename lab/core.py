"""图高模型、稀疏集合及无值域枚举的逻辑与比较宏。"""


def seq(*parts):
    return "\n".join(part for part in parts if part)


def format_code(code):
    depth = 0
    output = []
    for raw in code.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == "]":
            depth -= 1
        if depth < 0:
            raise ValueError("循环括号不匹配")
        output.append("  " * depth + line)
        if line == "[":
            depth += 1
    if depth:
        raise ValueError("循环括号未闭合")
    return "\n".join(output) + "\n"


class Model:
    # 两个零锚点永不写入：集合标记 -1、临时等值标记 -2
    SET_MARK = -1
    EQUAL_MARK = -2

    def __init__(self, array_base=-100):
        self.slots = {}
        self.flags = 0
        self.array_base = array_base

    def slot(self, name):
        if name not in self.slots:
            self.slots[name] = -len(self.slots) - 3
        return self.slots[name]

    @staticmethod
    def read(slot):
        return f"&{slot} ~1"

    @staticmethod
    def put(slot, expression):
        # 自环填充长度差异；正地址的标记最多经过两个边到达 0
        return f"&0 ^1 &{slot} ^4 &{slot} ^1 {expression} ^4"

    def const(self, slot, value):
        if value < 0:
            raise ValueError("普通数据槽只允许非负常量")
        return self.put(slot, f"&{value}")

    def copy(self, destination, source):
        return "" if destination == source else self.put(destination, self.read(source))

    @staticmethod
    def change(slot, operation):
        if operation not in ("@+", "@-"):
            raise ValueError("只接受自增或自减")
        return f"&0 ^1 &{slot} ^4 &{slot} *1 {operation} ^4"

    @staticmethod
    def once(condition, body):
        return seq(condition, "[", body, "&0", "]")

    @staticmethod
    def loop(condition, body):
        return seq(condition, "[", body, condition, "]")

    def branch(self, condition, yes, no=""):
        self.flags += 1
        flag = self.slot(f"分支{self.flags}")
        return seq(
            self.const(flag, 1),
            self.once(condition, seq(self.const(flag, 0), yes)),
            self.once(self.read(flag), no),
        )

    def zero(self, condition, body):
        return self.branch(condition, "", body)

    def conjunction(self, left, right, result):
        if result in (left, right):
            raise ValueError("合取输出不得覆盖输入")
        return seq(self.const(result, 0), self.once(self.read(left), self.once(self.read(right), self.const(result, 1))))

    def xor(self, left, right, result):
        if result in (left, right):
            raise ValueError("异或输出不得覆盖输入")
        return self.branch(self.read(left), self.branch(self.read(right), self.const(result, 0), self.const(result, 1)), self.copy(result, right))

    def key_address(self, key, pointer):
        if key == pointer:
            raise ValueError("键地址输出不得覆盖键")
        return self.put(pointer, self.read(key) + " @+")

    def write_marker(self, pointer, marker):
        if marker not in (0, self.SET_MARK, self.EQUAL_MARK):
            raise ValueError("正地址只接受零锚点标记")
        # 原单元是零或零锚点；选中后自环，常量标记通过深度 4 写入
        return f"&0 ^1 {self.read(pointer)} ^3 {self.read(pointer)} ^1 &{marker} ^4 &0 ^1"

    def set_add(self, key):
        pointer = self.slot("集合地址")
        return seq(self.key_address(key, pointer), self.write_marker(pointer, self.SET_MARK))

    def set_discard(self, key):
        pointer = self.slot("集合地址")
        return seq(self.key_address(key, pointer), self.write_marker(pointer, 0))

    def set_contains(self, key, result):
        if key == result:
            raise ValueError("集合查询输出不得覆盖键")
        return seq(self.const(result, 0), self.once(self.read(key) + " @+ ~1", self.const(result, 1)))

    def equal(self, left, right, result):
        """临时地址标记判断自然数相等，恢复原有集合标记。"""
        pointer, saved = self.slot("等值地址"), self.slot("等值原标记")
        if result in (left, right, pointer, saved) or {left, right} & {pointer, saved}:
            raise ValueError("等值输入输出不能使用内部槽或互相覆盖")
        return seq(
            self.key_address(left, pointer), self.const(saved, 0), self.const(result, 0),
            self.once(self.read(pointer) + " ~1", self.const(saved, 1)),
            self.write_marker(pointer, self.EQUAL_MARK),
            self.zero(self.read(right) + " @+ ~1 @+ @+", self.const(result, 1)),
            self.branch(self.read(saved), self.write_marker(pointer, self.SET_MARK), self.write_marker(pointer, 0)),
        )

    def compare(self, left, right, lt, eq, gt):
        """保留输入的自然数比较：相等走地址标记，否则同步抵消。"""
        outputs = {lt, eq, gt}
        if len(outputs) != 3 or outputs & {left, right}:
            raise ValueError("比较结果槽必须互异且不覆盖输入")
        a, b, run = (self.slot(name) for name in ("比较副本A", "比较副本B", "比较继续"))
        if {a, b, run} & {left, right, lt, eq, gt}:
            raise ValueError("比较参数不能使用内部工作槽")
        race = seq(
            self.copy(a, left), self.copy(b, right),
            self.conjunction(a, b, run),
            self.loop(self.read(run), seq(
                self.change(a, "@-"), self.change(b, "@-"), self.conjunction(a, b, run),
            )),
            self.branch(self.read(a), self.const(gt, 1), self.const(lt, 1)),
        )
        return seq(self.const(lt, 0), self.const(gt, 0), self.equal(left, right, eq), self.zero(self.read(eq), race))

    def compare_signed(self, sign_a, magnitude_a, sign_b, magnitude_b, lt, eq, gt):
        """符号/幅值输入的有符号比较，零的符号自动规范化。"""
        if len({lt, eq, gt}) != 3 or {lt, eq, gt} & {sign_a, magnitude_a, sign_b, magnitude_b}:
            raise ValueError("有符号比较结果槽必须互异且不覆盖输入")
        sa, sb, ml, me, mg = (self.slot(name) for name in ("有效符号A", "有效符号B", "幅值小于", "幅值等于", "幅值大于"))
        same = self.branch(self.read(sa), seq(self.copy(lt, mg), self.copy(eq, me), self.copy(gt, ml)),
                           seq(self.copy(lt, ml), self.copy(eq, me), self.copy(gt, mg)))
        different = self.branch(self.read(sa), self.const(lt, 1), self.const(gt, 1))
        signs_equal = self.slot("符号相等")
        return seq(
            self.copy(sa, sign_a), self.copy(sb, sign_b),
            self.zero(self.read(magnitude_a), self.const(sa, 0)),
            self.zero(self.read(magnitude_b), self.const(sb, 0)),
            self.const(lt, 0), self.const(eq, 0), self.const(gt, 0),
            self.equal(sa, sb, signs_equal),
            self.branch(self.read(signs_equal), seq(self.compare(magnitude_a, magnitude_b, ml, me, mg), same), different),
        )


class Tape:
    """两条交错负地址带；同一 lane 可由多个指针共同访问。"""

    def __init__(self, model, name, lane=0):
        if lane not in (0, 1):
            raise ValueError("当前模型只分配两条交错带")
        self.m = model
        self.lane = lane
        self.pointer = model.slot(f"{name}.指针")

    def reset(self):
        p = self.pointer
        return f"&0 ^1 &{p} ^5 &{p} ^1 &{self.m.array_base - self.lane} ^5"

    def move(self, forward=True):
        p = self.pointer
        operation = "@- @-" if forward else "@+ @+"
        return f"&0 ^1 &{p} ^5 &{p} *1 {operation} ^5"

    def read(self):
        return f"&{self.pointer} ~1 ~1"

    def put(self, expression):
        p = self.pointer
        return f"&0 ^1 &{p} ~1 ^4 &{p} ~1 ^1 {expression} ^4"


def compile_program(program):
    preview = Model()
    program(preview)
    model = Model(array_base=-len(preview.slots) - 3)
    code = program(model)
    if model.slots != preview.slots:
        raise ValueError("两遍静态生成的布局不一致")
    return format_code(code)
