"""数学参考仅在测试端使用，实验始终执行原版 Runtime。"""

from contextlib import redirect_stdout
from io import StringIO
import itertools
import json
import random
import unittest
from unittest.mock import patch

from lab.core import Model, Tape, compile_program, seq
from lab.programs import PROGRAMS
from lab.runtime import ROOT, Runtime, build
from lab.measure import dispatch_count


def evaluate(ir, stdin=""):
    rt = Runtime(can_direct_addressing=False)
    output = StringIO()
    with patch("sys.stdin", StringIO(stdin)), redirect_stdout(output):
        rt.run(ir)
    return output.getvalue(), rt


class ResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = {name: compile_program(program) for name, program in PROGRAMS.items()}
        cls.ir = {name: build(code) for name, code in cls.code.items()}

    def test_sparse_hash_equality_including_huge_naturals(self):
        huge = 10**1000 + 123
        cases = [(a, b) for a in range(8) for b in range(8)]
        cases += [(huge, huge), (huge, huge + 1), (0, huge), (huge, 0), (huge + 1, huge)]
        for a, b in cases:
            with self.subTest(a=str(a)[:25], b=str(b)[:25]):
                output, rt = evaluate(self.ir["equality"], f"{a}\n{b}\n")
                self.assertEqual(output, f"{int(a == b)}\n")
                self.assertTrue(all(value == 0 for address, value in rt.memory.items() if address > 0))
                self.assertEqual(rt.memory[-1], 0)
                self.assertEqual(rt.memory[-2], 0)

    def test_persistent_sparse_set_large_and_zero_keys(self):
        keys = [0, 1, 10**200, 256, 999999999999, 0]
        queries = [0, 1, 2, 255, 256, 10**200, 10**200 + 1]
        stdin = "\n".join(map(str, [len(keys), *keys, len(queries), *queries])) + "\n"
        output, rt = evaluate(self.ir["sparse-set"], stdin)
        self.assertEqual(output, "".join(f"{int(key in keys)}\n" for key in queries))
        self.assertEqual({address for address, value in rt.memory.items() if address > 0 and value != 0}, {key + 1 for key in keys})

    def test_marked_scalar_values_survive_all_operations(self):
        def program(m):
            key, a, b, result = (m.slot(name) for name in ("键", "A", "B", "等值"))
            parts = []
            for value in range(12):
                parts += [m.const(key, value), m.set_add(key)]
            parts += [m.const(a, 0), m.const(b, 7), m.change(a, "@+"), m.change(a, "@-"),
                      m.copy(a, b), m.equal(a, b, result), m.read(result) + " @print",
                      m.const(key, 6), m.set_discard(key), m.set_contains(key, result), m.read(result) + " @print",
                      m.const(key, 7), m.set_contains(key, result), m.read(result) + " @print"]
            return seq(*parts)

        output, rt = evaluate(build(compile_program(program)))
        self.assertEqual(output, "1\n0\n1\n")
        self.assertEqual(rt.memory[7], 0)
        self.assertEqual(rt.memory[8], -1)

    def test_equality_restores_each_possible_prior_set_membership(self):
        for left_present, right_present, same in itertools.product((False, True), repeat=3):
            def program(m):
                a, b, result = (m.slot(name) for name in ("A", "B", "等值"))
                parts = [m.const(a, 5), m.const(b, 5 if same else 8)]
                if left_present:
                    parts.append(m.set_add(a))
                if right_present:
                    parts.append(m.set_add(b))
                parts += [m.equal(a, b, result), m.read(result) + " @print"]
                return seq(*parts)

            output, rt = evaluate(build(compile_program(program)))
            self.assertEqual(output, f"{int(same)}\n")
            expected = ({6} if left_present else set()) | ({6 if same else 9} if right_present else set())
            self.assertEqual({address for address, value in rt.memory.items() if address > 0 and value != 0}, expected)

    def test_natural_compare_exhaustive_and_equal_huge_values(self):
        cases = list(itertools.product(range(16), repeat=2)) + [(1000, 3), (256, 300), (10**500, 10**500), (10**500, 0)]
        for a, b in cases:
            output, _ = evaluate(self.ir["comparison"], f"{a}\n{b}\n")
            self.assertEqual(output, f"{int(a < b)}\n{int(a == b)}\n{int(a > b)}\n")

    def test_signed_pair_comparison_without_negative_value_enumeration(self):
        for a, b in itertools.product(range(-8, 9), repeat=2):
            output, _ = evaluate(self.ir["signed-comparison"], f"{int(a < 0)}\n{abs(a)}\n{int(b < 0)}\n{abs(b)}\n")
            self.assertEqual(output, f"{int(a < b)}\n{int(a == b)}\n{int(a > b)}\n")
        output, _ = evaluate(self.ir["signed-comparison"], "1\n0\n0\n0\n")
        self.assertEqual(output, "0\n1\n0\n")

    def test_comparison_sort_above_byte_domain(self):
        rng = random.Random(20261107)
        cases = [[], [0], [500, 0, 257, 500, 999, 1], list(range(10)), list(reversed(range(10))), [1000] * 5]
        cases += [[rng.randrange(400) for _ in range(rng.randrange(9))] for _ in range(20)]
        for values in cases:
            output, _ = evaluate(self.ir["comparison-sort"], "\n".join(map(str, [len(values), *values])) + "\n")
            self.assertEqual(output, "".join(f"{value}\n" for value in sorted(values)))

    def test_two_interleaved_tapes_and_reverse_navigation(self):
        def program(m):
            a, b = Tape(m, "A", 0), Tape(m, "B", 1)
            parts = [a.reset(), b.reset()]
            for x, y in [(0, 5), (7, 0), (9, 8)]:
                parts += [a.put(f"&{x}"), b.put(f"&{y}"), a.move(), b.move()]
            for _ in range(3):
                parts += [a.move(False), b.move(False), a.read() + " @print", b.read() + " @print"]
            return seq(*parts)

        output, _ = evaluate(build(compile_program(program)))
        self.assertEqual(output, "9\n8\n7\n0\n0\n5\n")

    def test_binary_full_adder_all_inputs_and_long_values(self):
        rng = random.Random(77)
        for width in [0, 1, 2, 4, 8, 31, 127, 512, 1024]:
            samples = [(0, 0), ((1 << width) - 1, 1 if width else 0), (rng.getrandbits(width), rng.getrandbits(width))]
            if width < 3:
                samples = list(itertools.product(range(1 << width), repeat=2))
            for a, b in samples:
                text_a = format(a, f"0{width}b") if width else ""
                text_b = format(b, f"0{width}b") if width else ""
                output, _ = evaluate(self.ir["binary-add"], f"{width}\n{text_a}\n{text_b}\n")
                self.assertEqual(output, format(a + b, f"0{width + 1}b") + "\n")

    def test_no_direct_addressing_and_no_new_runtime_operations(self):
        for name, code in self.code.items():
            self.assertLessEqual({token for token in code.split() if token.startswith("@")},
                                 {"@input", "@print", "@input_as_char", "@print_as_char", "@+", "@-"})
            target = ROOT / "examples" / f"{name}.pp3"
            self.assertEqual(code, target.read_text(encoding="ascii"))

    def test_equality_dispatches_do_not_scale_with_numeric_magnitude(self):
        counts_equal = {dispatch_count(self.ir["equality"], f"{value}\n{value}\n") for value in [0, 3, 10**1000]}
        counts_unequal = {dispatch_count(self.ir["equality"], f"{value}\n{value + 1}\n") for value in [0, 3, 10**1000]}
        self.assertEqual(len(counts_equal), 1)
        self.assertEqual(len(counts_unequal), 1)

    def test_binary_add_dispatch_growth_is_linear_in_width(self):
        counts = []
        for width in [8, 16, 24]:
            text = f"{width}\n" + "1" * width + "\n" + "0" * (width - 1) + "1\n"
            counts.append(dispatch_count(self.ir["binary-add"], text))
        self.assertEqual(counts[2] - counts[1], counts[1] - counts[0])

    def test_tapes_work_while_positive_addresses_are_marked(self):
        def program(m):
            a, b = Tape(m, "A", 0), Tape(m, "B", 1)
            key = m.slot("键")
            parts = []
            for value in range(10):
                parts += [m.const(key, value), m.set_add(key)]
            parts += [a.reset(), b.reset(), a.put("&7"), b.put("&0"), a.move(), b.move(),
                      a.put("&0"), b.put("&9"), a.move(False), b.move(False),
                      a.read() + " @print", b.read() + " @print"]
            return seq(*parts)

        output, _ = evaluate(build(compile_program(program)))
        self.assertEqual(output, "7\n0\n")

    def test_generic_graph_height_write_theorem_on_all_small_rooted_graphs(self):
        # 测试枚举小图来验证定理；生成的赋值算法本身不枚举任何输入值
        for edges in itertools.product(range(4), repeat=3):
            distances = []
            valid = True
            for source in range(1, 4):
                node, seen = source, set()
                while node and node not in seen:
                    seen.add(node)
                    node = edges[node - 1]
                if node:
                    valid = False
                    break
                distances.append(len(seen))
            if not valid:
                continue
            depth = max(distances) + 2
            for old, new in itertools.product(range(4), repeat=2):
                rt = Runtime(can_direct_addressing=False)
                rt.memory.update({index + 1: value for index, value in enumerate(edges)})
                rt.memory[-10] = old
                code = f"&0 ^1 &-10 ^{depth} &-10 ^1 &{new} ^{depth}"
                rt.run(build(code))
                self.assertEqual(rt.memory[-10], new, (edges, old, new))
                self.assertEqual([rt.memory[i] for i in range(1, 4)], list(edges))

    def test_positive_cycle_is_a_real_counterexample_to_the_write_precondition(self):
        rt = Runtime(can_direct_addressing=False)
        rt.memory[-10] = 1
        rt.memory[1] = 1
        rt.run(build("&0 ^1 &-10 ^4 &-10 ^1 &2 ^4"))
        self.assertNotEqual(rt.memory[-10], 2)
        self.assertEqual(rt.memory[1], -10)

    def test_one_fixed_offset_cannot_avoid_reserved_addresses_for_all_integers(self):
        for offset in [-100, 0, 1, 100, 10**100]:
            source = -3 - offset
            self.assertEqual(source + offset, -3)

    def test_standard_view_mutation_interface_and_eof_are_preserved(self):
        with patch("sys.stdin", StringIO("")), self.assertRaises(EOFError):
            Runtime(can_direct_addressing=False).run(self.ir["equality"])
        for code in ["#0", "$0", "%0", "&0 [ #1 ]"]:
            with self.assertRaises(ValueError):
                build(code)

    def test_every_documented_example_matches_its_exact_sample(self):
        samples = json.loads((ROOT / "examples/cases.json").read_text(encoding="utf-8"))
        self.assertEqual(set(samples), set(PROGRAMS))
        for name, cases in samples.items():
            for case in cases:
                with self.subTest(example=name, case=case["name"]):
                    output, _ = evaluate(self.ir[name], case["stdin"])
                    self.assertEqual(output, case["stdout"])

    def test_findings_have_documents_examples_and_correct_status(self):
        catalog = json.loads((ROOT / "research/findings.json").read_text(encoding="utf-8"))
        entries = catalog["findings"]
        self.assertEqual(len({entry["id"] for entry in entries}), len(entries))
        for entry in entries:
            self.assertEqual(entry["status"], "proved")
            self.assertTrue((ROOT / entry["document"]).is_file())
            self.assertTrue(set(entry["examples"]) <= set(PROGRAMS))

    def test_simple_alias_contracts_are_rejected_during_generation(self):
        m = Model()
        a, b, result = (m.slot(name) for name in ("A", "B", "输出"))
        for invoke in [lambda: m.conjunction(a, b, a), lambda: m.xor(a, b, b),
                       lambda: m.key_address(a, a), lambda: m.equal(a, b, a),
                       lambda: m.compare(a, b, result, result, result)]:
            with self.assertRaises(ValueError):
                invoke()


if __name__ == "__main__":
    unittest.main()
