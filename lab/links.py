"""局部路由头、独立记录、所有权拼接与空闲链；只生成纯 PP3。"""

from lab.core import seq


class Reference:
    """引用只允许零或指向永久零头的记录地址，数据到零的图高为一。"""

    @staticmethod
    def put(slot, expression):
        return f"&0 ^1 &{slot} ^3 &{slot} ^1 {expression} ^3"

    @staticmethod
    def copy(destination, source):
        return "" if destination == source else Reference.put(destination, f"&{source} ~1")

    @staticmethod
    def next(slot):
        # 交换保留旧记录地址，再通过显式字段偏移读取后继，避免先清空源引用
        return f"&0 ^1 &{slot} ^3 &{slot} *1 @- @- @- ~1 ^3"

    @staticmethod
    def bump(slot):
        return f"&0 ^1 &{slot} ^3 &{slot} *1 @- @- @- @- ^3"


class RecordHeap:
    """每个记录有零头、幅值、符号、后继四个单元，分配与回收不扫描。"""

    MAGNITUDE = 1
    SIGN = 2
    NEXT = 3

    def __init__(self, model):
        self.m = model
        self.bump = model.slot("记录堆.未使用地址")
        self.free = model.slot("记录堆.空闲头")

    def initialize(self):
        # 只在全新运行器中调用一次；记录堆与 Tape 使用不同示例，不混用布局
        return Reference.put(self.bump, f"&{self.m.array_base}")

    def field_address(self, reference, field):
        if field not in (self.MAGNITUDE, self.SIGN, self.NEXT):
            raise ValueError("只能访问幅值、符号和后继，永久零头不可写")
        return self.m.read(reference) + " " + "@- " * field

    def read(self, reference, field):
        return self.field_address(reference, field) + "~1"

    def put(self, reference, field, expression):
        address = self.field_address(reference, field)
        depth = 3 if field == self.NEXT else 4
        return f"&0 ^1 {address} ^{depth} {address} ^1 {expression} ^{depth}"

    def allocate(self, node, magnitude, sign):
        if len({node, magnitude, sign, self.bump, self.free}) != 5:
            raise ValueError("分配器、节点地址、幅值和符号必须使用不同槽")
        acquire = self.m.branch(
            self.m.read(self.free),
            seq(Reference.copy(node, self.free), Reference.next(self.free)),
            seq(Reference.copy(node, self.bump), Reference.bump(self.bump)),
        )
        return seq(acquire,
                   self.put(node, self.MAGNITUDE, self.m.read(magnitude)),
                   self.put(node, self.SIGN, self.m.read(sign)),
                   self.put(node, self.NEXT, "&0"))

    def release(self, node):
        if node in (self.bump, self.free):
            raise ValueError("释放输入不能是分配器自身的引用槽")
        # 调用方必须保证节点已从活动结构摘下、没有重复释放
        return seq(self.put(node, self.NEXT, self.m.read(self.free)), Reference.copy(self.free, node))


class RecordList:
    def __init__(self, heap, name):
        self.heap = heap
        self.m = heap.m
        self.head = self.m.slot(f"{name}.表头")
        self.tail = self.m.slot(f"{name}.表尾")

    def _check_node(self, node):
        if node in (self.head, self.tail):
            raise ValueError("节点工作引用不得覆盖表头或表尾")

    def append(self, node):
        self._check_node(node)
        return seq(self.m.branch(
            self.m.read(self.tail),
            self.heap.put(self.tail, RecordHeap.NEXT, self.m.read(node)),
            Reference.copy(self.head, node),
        ), Reference.copy(self.tail, node))

    def prepend(self, node):
        self._check_node(node)
        return seq(
            self.heap.put(node, RecordHeap.NEXT, self.m.read(self.head)),
            self.m.zero(self.m.read(self.tail), Reference.copy(self.tail, node)),
            Reference.copy(self.head, node),
        )

    def pop(self, node):
        self._check_node(node)
        # 前置条件是非空；返回摘下的节点，调用方决定读取、转移还是释放
        return seq(Reference.copy(node, self.head), Reference.next(self.head),
                   self.m.zero(self.m.read(self.head), Reference.put(self.tail, "&0")),
                   self.heap.put(node, RecordHeap.NEXT, "&0"))

    def concat(self, other):
        if self.heap is not other.heap or {self.head, self.tail} & {other.head, other.tail}:
            raise ValueError("拼接需要同堆的两个不同链表，且节点所有权互不重叠")
        join = seq(self.m.branch(
            self.m.read(self.tail),
            self.heap.put(self.tail, RecordHeap.NEXT, self.m.read(other.head)),
            Reference.copy(self.head, other.head),
        ), Reference.copy(self.tail, other.tail))
        return seq(self.m.once(self.m.read(other.head), join),
                   Reference.put(other.head, "&0"), Reference.put(other.tail, "&0"))


def read_encoded_list(model, heap, target, prepend=False):
    count, magnitude, sign, node = (model.slot(name) for name in ("链输入.数量", "链输入.幅值", "链输入.符号", "链输入.节点"))
    attach = target.prepend(node) if prepend else target.append(node)
    return seq(model.put(count, "@input"), model.loop(model.read(count), seq(
        model.put(sign, "@input"), model.put(magnitude, "@input"),
        heap.allocate(node, magnitude, sign), attach, model.change(count, "@-"),
    )))


def print_node(model, heap, node):
    magnitude, sign = model.slot("链输出.幅值"), model.slot("链输出.符号")
    return seq(model.put(magnitude, heap.read(node, RecordHeap.MAGNITUDE)),
               model.put(sign, heap.read(node, RecordHeap.SIGN)),
               model.once(model.read(magnitude), model.once(model.read(sign), "&45 @print_as_char")),
               model.read(magnitude) + " @print")


def drain(model, heap, target):
    node = model.slot("链输出.摘下节点")
    return model.loop(model.read(target.head), seq(target.pop(node), print_node(model, heap, node), heap.release(node)))


def value_chain(model):
    # 用户原构造，独立零内存运行；不与本项目的 -1/-2 锚点布局混用
    return "&-1 ^2 @input [ ^3 ^2 @input ] &-1 ~1 [ @print ~1 ]"


def record_queue(model):
    heap = RecordHeap(model)
    target = RecordList(heap, "队列")
    return seq(heap.initialize(), read_encoded_list(model, heap, target), drain(model, heap, target))


def record_stack(model):
    heap = RecordHeap(model)
    target = RecordList(heap, "栈")
    return seq(heap.initialize(), read_encoded_list(model, heap, target, prepend=True), drain(model, heap, target))


def record_splice(model):
    heap = RecordHeap(model)
    first, second = RecordList(heap, "甲"), RecordList(heap, "乙")
    return seq(heap.initialize(), read_encoded_list(model, heap, first), read_encoded_list(model, heap, second),
               first.concat(second), drain(model, heap, first))


def record_ring(model):
    heap = RecordHeap(model)
    target = RecordList(heap, "环")
    cursor, count = model.slot("环.游标"), model.slot("环.剩余")
    # 加载宏会清空自己的计数槽，因此单独按节点遍历计数后再闭环
    load = read_encoded_list(model, heap, target)
    count_nodes = seq(Reference.copy(cursor, target.head), model.loop(model.read(cursor), seq(
        model.change(count, "@+"), Reference.next(cursor),
    )))
    close_ring = heap.put(target.tail, RecordHeap.NEXT, model.read(target.head))
    return seq(heap.initialize(), load, count_nodes,
               model.once(model.read(target.head), close_ring), Reference.copy(cursor, target.head),
               model.loop(model.read(count), seq(print_node(model, heap, cursor), Reference.next(cursor), model.change(count, "@-"))))


PROGRAMS = {
    "value-chain": value_chain,
    "record-queue": record_queue,
    "record-stack": record_stack,
    "record-splice": record_splice,
    "record-ring": record_ring,
}
