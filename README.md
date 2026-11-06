# PP3 Lab

研究 PP3 的存储、寻址、数据表示和算法能力。目标是寻找可组合的通用技巧，减少用有限值域查表、逐值分类或固定字节桶代替算法的做法。

本项目独立于 [PP3 Challenges](https://github.com/JDK8u341/PP3-Challenges)。以下发现已经提供数学契约、纯 DSL 示例和自动测试；实验不修改 PP3 运行器，不启用直接寻址，不调用 cup 或自定义运算。

## 本轮发现

| 编号 | 结论 | 实际适用范围 |
| --- | --- | --- |
| R01 | 用函数图描述间接寻址，按到零路径的最大长度选择深度 | 有明确的有根路径条件，不适用于任意混乱内存 |
| R02 | 目标自环填充路径长度差异，统一写入与读改写 | 本实现支持正地址标记、非负标量与零值 |
| R03 | 数值地址上的稀疏集合：插入、删除、查询 | 宿主解析和资源范围内的自然数键，固定数量的 DSL 指令 |
| R04 | 临时地址标记做等值判断并恢复集合 | 任意自然数，不按数值逐次抵消；不是恒定真实耗时 |
| R05 | 保留输入的大小比较，先快速等值，再同步抵消 | 不枚举输入域；不等时仍与较小幅值有关 |
| R06 | 符号/幅值编码支持有符号顺序比较 | 不需要分类所有危险负地址；输入必须已经编码 |
| R07 | 两条交错负地址带与多个游标 | 顺序、反向访问，两个带之间不冲突 |
| R08 | 逐位全加器实现按位数线性的二进制加法 | 已验证 1024 位和全长进位；输出固定位宽 |
| R09 | 基于比较的自然数冒泡排序 | 不分桶、不限于 0..255；不是高性能大数排序 |

完整记录见 [研究目录](research/findings.json)、[图模型](docs/01-graph-model.md)、[集合与等值](docs/02-address-marking.md)、[比较与排序](docs/03-comparison.md)、[双带与二进制](docs/04-tapes-and-bits.md)。

## 可重复结果

- 等值示例读取 1、10、100、1000 位十进制自然数时，测量样例均为 **115 次分派**，相等与相邻不等均如此。这是整个示例的计数，不是单个 `equal()` 宏的计数。
- 二进制加法在全长进位样例上，8..1024 位的测量符合 **453w+100 次分派**。1024 位为 463972 次；这是该类输入的测量公式，不是所有输入的精确成本公式。
- 小图验证覆盖三个非零结点的全部 16 个有根函数图及每图 16 个写入组合；另保存了正地址自环导致赋值失败的最小反例。

原始数据见 [dispatch-counts.json](results/dispatch-counts.json)，计数方法与性能边界见 [验证与成本模型](docs/06-validation.md)。没有把分派次数等同于机器指令、内存访问次数或 CPU 耗时。

## 运行

```text
git clone --recurse-submodules https://github.com/JDK8u341/PP3-Lab.git
cd PP3-Lab
python tools/run.py equality
python tools/run.py comparison-sort
python tools/run.py binary-add
python -B -m unittest discover -v
python tools/measure.py
```

各示例精确输入输出和合法定义域见 [examples/README.md](examples/README.md)。它们是研究构造，不是为任意非法输入设计的命令行产品：例如自然数输入不得为负，二进制输入必须遵守位宽与行结构。

源码生成器仅在编译期展开，输入值不会送入 Python 计算。可用 `python tools/generate.py all` 重新生成全部 `.pp3`；测试检查展开结果逐字一致。

## 条件与目录

固定上游提交为 `aceb4c532cf475f7b69fb623affc81c9f70e8c48`，执行条件为：

```python
IRBuilder(op_map=std_register)
Runtime(can_direct_addressing=False)
```

```text
docs/       中文推导、反例、性能与边界
research/   发现目录及后续研究清单
examples/   七份纯 DSL 示例、精确输入输出样例
lab/        静态宏、程序构造、原版运行器入口
tools/      生成、执行和计数命令
tests/      性质、反例、接口和示例测试
results/    可重复测量的原始结果
vendor/PP3/ 固定版本运行器子模块
```

尚未解决的内容见 [边界与下一步](docs/05-limits.md)：任意未编码有符号整数的通用读写、非计数式的大数顺序比较、一般图的指针安全，以及完整 PP3 自解释器均不在已证明范围内。

原创代码与文档采用 GPL-3.0，见 [LICENSE](LICENSE)。上游运行器保留其自身许可；固定子模块没有修改。本文结论源于本项目构造和测试，不声称这是全局首次发现。
