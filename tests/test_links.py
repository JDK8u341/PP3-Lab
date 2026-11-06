"""原始伪链表、记录路由、拼接、环和复用的性质验证。"""

from contextlib import redirect_stdout
from io import StringIO
import itertools
import random
import unittest
from unittest.mock import patch

from lab.core import Model, compile_program, seq
from lab.links import RecordHeap, RecordList, Reference, read_encoded_list
from lab.measure import dispatch_count
from lab.programs import PROGRAMS
from lab.runtime import Runtime, build


def execute(ir, stdin="", runtime=None):
    rt = runtime if runtime is not None else Runtime(can_direct_addressing=False)
    output = StringIO()
    with patch("sys.stdin", StringIO(stdin)), redirect_stdout(output):
        rt.run(ir)
    return output.getvalue(), rt


def encoded(values):
    return str(len(values)) + "\n" + "".join(f"{int(value < 0)}\n{abs(value)}\n" for value in values)


class LinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ir = {name: build(compile_program(PROGRAMS[name])) for name in (
            "value-chain", "record-queue", "record-stack", "record-splice", "record-ring",
        )}

    def test_original_value_chain_accepts_distinct_negative_and_positive_nodes(self):
        for values in [[], [5], [5, 6, 7], [-2, -3, 4], [10**300, -10**300]]:
            with self.subTest(values=values):
                output, _ = execute(self.ir["value-chain"], "\n".join(map(str, [*values, 0])) + "\n")
                self.assertEqual(output, "".join(f"{value}\n" for value in values))

    def test_original_duplicate_nodes_really_form_cycles(self):
        # 只运行构建段再有限读取，避免把不终止的完整程序交给测试
        load = build("&-1 ^2 @input [ ^3 ^2 @input ]")
        for values, cycle in [([5, 5, 0], [5]), ([5, 6, 5, 0], [5, 6]), ([-1, 0], [-1])]:
            _, rt = execute(load, "\n".join(map(str, values)) + "\n")
            cursor = rt.memory[-1]
            observed = []
            for _ in range(len(cycle) * 2):
                observed.append(cursor)
                cursor = rt.memory[cursor]
            self.assertEqual(observed, cycle * 2)

    def test_queue_stack_and_ring_preserve_duplicate_zero_and_signed_payloads(self):
        cases = [[], [0], [5, 5, 0, -1, -2, -1], [-(10**300), 0, 10**300, -(10**300)]]
        rng = random.Random(20261107)
        cases += [[rng.randrange(-4, 5) for _ in range(rng.randrange(25))] for _ in range(20)]
        for name in ("record-queue", "record-stack", "record-ring"):
            for values in cases:
                with self.subTest(name=name, length=len(values)):
                    output, _ = execute(self.ir[name], encoded(values))
                    expected = list(reversed(values)) if name == "record-stack" else values
                    self.assertEqual(output, "".join(f"{value}\n" for value in expected))

    def test_splice_all_empty_nonempty_combinations(self):
        for first, second in itertools.product(([], [0], [5, 5, -1]), repeat=2):
            output, _ = execute(self.ir["record-splice"], encoded(first) + encoded(second))
            self.assertEqual(output, "".join(f"{value}\n" for value in first + second))

    def test_negative_zero_is_printed_as_zero(self):
        output, _ = execute(self.ir["record-queue"], "2\n1\n0\n1\n0\n")
        self.assertEqual(output, "0\n0\n")

    def test_free_list_reuses_node_without_advancing_bump(self):
        model = Model(array_base=-200)
        heap = RecordHeap(model)
        a, b, saved = (model.slot(name) for name in ("节点甲", "节点乙", "未用地址快照"))
        magnitude, sign = model.slot("幅值"), model.slot("符号")
        setup = seq(heap.initialize(), model.const(magnitude, 7), model.const(sign, 0),
                    heap.allocate(a, magnitude, sign), Reference.copy(saved, heap.bump), heap.release(a),
                    model.const(magnitude, 0), model.const(sign, 1), heap.allocate(b, magnitude, sign))
        _, rt = execute(build(setup))
        self.assertEqual(rt.memory[a], rt.memory[b])
        self.assertEqual(rt.memory[heap.bump], rt.memory[saved])
        self.assertEqual(rt.memory[heap.free], 0)
        self.assertEqual(rt.memory[rt.memory[b]], 0)
        self.assertEqual(rt.memory[rt.memory[b] - RecordHeap.MAGNITUDE], 0)
        self.assertEqual(rt.memory[rt.memory[b] - RecordHeap.SIGN], 1)
        self.assertEqual(rt.memory[rt.memory[b] - RecordHeap.NEXT], 0)

    def test_record_queue_append_dispatches_do_not_depend_on_length(self):
        counts = []
        for size in (0, 1, 8, 64):
            model = Model(array_base=-200)
            heap = RecordHeap(model)
            target = RecordList(heap, "队列")
            node, magnitude, sign = (model.slot(name) for name in ("待追加节点", "载荷", "符号"))
            setup = seq(heap.initialize(), read_encoded_list(model, heap, target),
                        model.const(magnitude, 13), model.const(sign, 0), heap.allocate(node, magnitude, sign))
            operation = target.append(node)
            _, rt = execute(build(setup), encoded([0] * size))
            counts.append(dispatch_count(build(operation), "", runtime=rt))
        self.assertNotEqual(counts[0], counts[1])
        self.assertEqual(len(set(counts[1:])), 1)

    def test_reuse_chain_append_dispatches_do_not_depend_on_length(self):
        counts = []
        for size in (1, 8, 64):
            inputs = iter(map(str, [*range(5, 5 + size), 0]))
            rt = Runtime(can_direct_addressing=False)
            with patch("builtins.input", side_effect=lambda: next(inputs)), redirect_stdout(StringIO()):
                rt.run(build("&-1 ^2 @input [ ^3 ^2 @input ]"))
            before = {address: value for address, value in rt.memory.items()}
            counts.append(dispatch_count(build("@input ^3 ^2"), "1000\n", runtime=rt))
            self.assertEqual(rt.memory[0], 1000)
            self.assertEqual(rt.memory[5 + size - 1], 1000)
            for address, value in before.items():
                if address not in (0, 5 + size - 1):
                    self.assertEqual(rt.memory[address], value)
        self.assertEqual(len(set(counts)), 1)

    def test_concat_transfers_ownership_and_keeps_record_headers_zero(self):
        model = Model(array_base=-200)
        heap = RecordHeap(model)
        first, second = RecordList(heap, "甲"), RecordList(heap, "乙")
        code = seq(heap.initialize(), read_encoded_list(model, heap, first),
                   read_encoded_list(model, heap, second), first.concat(second))
        _, rt = execute(build(code), encoded([5, 5]) + encoded([0, -7]))
        self.assertEqual(rt.memory[second.head], 0)
        self.assertEqual(rt.memory[second.tail], 0)
        cursor = rt.memory[first.head]
        addresses, values = [], []
        while cursor:
            self.assertNotIn(cursor, addresses)
            addresses.append(cursor)
            self.assertEqual(rt.memory[cursor], 0)
            values.append(rt.memory[cursor - RecordHeap.MAGNITUDE])
            cursor = rt.memory[cursor - RecordHeap.NEXT]
        self.assertEqual(values, [5, 5, 0, 7])
        self.assertEqual(len(set(addresses)), 4)
        self.assertEqual(rt.memory[first.tail], addresses[-1])

    def test_logical_ring_does_not_break_scalar_or_set_macros(self):
        model = Model(array_base=-200)
        heap = RecordHeap(model)
        queue = RecordList(heap, "环")
        key, result = model.slot("集合键"), model.slot("集合结果")
        close = heap.put(queue.tail, RecordHeap.NEXT, model.read(queue.head))
        code = seq(heap.initialize(), read_encoded_list(model, heap, queue), close,
                   model.const(key, 6), model.set_add(key), model.change(key, "@+"), model.change(key, "@-"),
                   model.set_contains(key, result), model.read(result) + " @print")
        output, rt = execute(build(code), encoded([5, 5, 0]))
        self.assertEqual(output, "1\n")
        cursor = rt.memory[queue.head]
        for _ in range(3):
            self.assertEqual(rt.memory[cursor], 0)
            cursor = rt.memory[cursor - RecordHeap.NEXT]
        self.assertEqual(cursor, rt.memory[queue.head])

    def test_splice_dispatches_do_not_depend_on_list_length(self):
        counts = []
        for size in (1, 8, 64):
            model = Model(array_base=-200)
            heap = RecordHeap(model)
            first, second = RecordList(heap, "甲"), RecordList(heap, "乙")
            setup = seq(heap.initialize(), read_encoded_list(model, heap, first), read_encoded_list(model, heap, second))
            operation = first.concat(second)
            _, rt = execute(build(setup), encoded([0] * size) + encoded([1] * size))
            counts.append(dispatch_count(build(operation), "", runtime=rt))
        self.assertEqual(len(set(counts)), 1)

    def test_ownership_and_header_contracts_reject_obvious_misuse(self):
        model = Model()
        heap = RecordHeap(model)
        queue = RecordList(heap, "甲")
        other = RecordList(heap, "乙")
        other.tail = queue.head
        node = model.slot("节点")
        for call in (lambda: queue.concat(queue), lambda: queue.concat(other), lambda: queue.append(queue.head),
                     lambda: heap.put(node, 0, "&123"), lambda: heap.release(heap.free)):
            with self.assertRaises(ValueError):
                call()

    def test_two_list_nodes_with_identical_payloads_have_distinct_identities(self):
        model = Model(array_base=-200)
        heap = RecordHeap(model)
        target = RecordList(heap, "重值")
        setup = seq(heap.initialize(), read_encoded_list(model, heap, target))
        _, rt = execute(build(setup), encoded([7, 7, 0, -1]))
        first = rt.memory[target.head]
        second = rt.memory[first - RecordHeap.NEXT]
        third = rt.memory[second - RecordHeap.NEXT]
        fourth = rt.memory[third - RecordHeap.NEXT]
        self.assertEqual([rt.memory[node - RecordHeap.MAGNITUDE] for node in (first, second, third, fourth)], [7, 7, 0, 1])
        self.assertEqual([rt.memory[node - RecordHeap.SIGN] for node in (first, second, third, fourth)], [0, 0, 0, 1])
        self.assertEqual(len({first, second, third, fourth}), 4)

    def test_one_node_lists_support_pop_release_and_free_list_reuse(self):
        model = Model(array_base=-200)
        heap = RecordHeap(model)
        queue = RecordList(heap, "单节点队列")
        magnitude, sign, first, second, out = (model.slot(name) for name in ("幅值", "符号", "首节点", "次节点", "摘下节点"))
        code = seq(heap.initialize(), model.const(magnitude, 42), model.const(sign, 0),
                   heap.allocate(first, magnitude, sign), queue.append(first),
                   queue.pop(out), heap.release(out),
                   model.const(magnitude, 0), model.const(sign, 1),
                   heap.allocate(second, magnitude, sign), queue.append(second),
                   model.read(queue.head) + " @print", heap.read(second, RecordHeap.MAGNITUDE) + " @print",
                   heap.read(second, RecordHeap.SIGN) + " @print")
        output, rt = execute(build(code))
        self.assertEqual(rt.memory[first], rt.memory[second])
        self.assertEqual(output, f"{rt.memory[second]}\n0\n1\n")

    def test_mixed_allocations_and_releases_keep_live_and_free_nodes_disjoint(self):
        model = Model(array_base=-200)
        heap = RecordHeap(model)
        queue = RecordList(heap, "混合队列")
        node, out, magnitude, sign = (model.slot(name) for name in ("新节点", "摘下节点", "幅值", "符号"))
        rt = Runtime(can_direct_addressing=False)
        append_ir = build(seq(model.put(magnitude, "@input"), model.const(sign, 0),
                              heap.allocate(node, magnitude, sign), queue.append(node)))
        remove_ir = build(seq(queue.pop(out), heap.release(out)))
        self.assertGreater(min(model.slots.values()), model.array_base)
        rt.run(build(heap.initialize()))
        expected = []
        seen_addresses = set()
        rng = random.Random(442)
        live_max = 0
        for _ in range(120):
            if not expected or rng.randrange(3):
                value = rng.randrange(6)
                execute(append_ir, f"{value}\n", runtime=rt)
                expected.append(value)
                seen_addresses.add(rt.memory[node])
                live_max = max(live_max, len(expected))
            else:
                rt.run(remove_ir)
                expected.pop(0)

            def walk(head):
                addresses, values = [], []
                current = rt.memory[head]
                while current:
                    self.assertNotIn(current, addresses)
                    self.assertEqual(rt.memory[current], 0)
                    addresses.append(current)
                    values.append(rt.memory[current - RecordHeap.MAGNITUDE])
                    current = rt.memory[current - RecordHeap.NEXT]
                return addresses, values

            live, values = walk(queue.head)
            free, _ = walk(heap.free)
            self.assertEqual(values, expected)
            self.assertFalse(set(live) & set(free))
            self.assertEqual(set(live) | set(free), seen_addresses)
            self.assertEqual(rt.memory[queue.tail], live[-1] if live else 0)
        self.assertEqual(len(seen_addresses), live_max)


if __name__ == "__main__":
    unittest.main()
