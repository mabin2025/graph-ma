# graph-ma

基于真实源码，用简洁流程图、核心代码和真实结果图，生成便于阅读与复盘的中文项目解读。

## 适用场景

- 项目接手、架构梳理、调用链和数据流分析。
- Agent、RAG、记忆、规划路由、工具执行和任务调度分析。
- 机器学习与 Notebook 项目的数据、特征、训练评估和融合解读。
- 结合真实项目进行技术学习、项目复盘与面试准备。

## 默认产物

一份 Markdown、一张简洁主图，以及按需选择的子模块 SVG、核心代码片段与真实结果图。图讲流程，代码讲实现，结果图讲观察，正文讲原因与边界；不为每个模块凑齐所有材料。

主图通常保留 4～7 个阶段，子图围绕一个问题展开，详细参数和风险放正文。代码片段说明来源及精简情况，结果图区分历史输出与本次运行。复盘或面试场景可补少量项目相关问答。

事实来源区分源码确认、本地文件实测、历史输出、本次运行、合理推断和待验证。SVG 进行 XML 与渲染检查，结果图检查可读性与来源，Markdown 检查图片链接。默认仅修改指定文档与图形资产，增量编辑保留用户补充，不修改业务代码。

多模块或持续维护时，可在文档目录保存轻量 `analysis.json`，把模块、结论、源码位置、章节和图形关联起来。文件摘要检测已提交与未提交的内容变化，按记录的依赖定位待更新章节；Notebook 分别记录代码与历史输出变化。项目已有 Understand Anything 图谱时可复用其导航信息，关键结论仍回到当前源码核实。

## 使用示例

```text
使用 graph-ma 分析当前代码库，生成中文项目解读到指定文档目录。
主图与子图保持简洁，关键模块附少量核心代码。
有真实结果图时解释它支持的结论，关键事实注明源码位置。
```

```text
使用 graph-ma 解读这个机器学习项目，写入我的 Obsidian 项目复盘目录。
重点解释数据筛选、特征处理、训练评估和模型融合。
复用 Notebook 的核心结果图并标注历史输出，补几个与项目相关的面试题。
```

如需先审阅主图，可以明确要求：

```text
使用 graph-ma 解读这个项目，先完成项目主图并等我确认，
确认后再继续绘制子模块图和编写正文。
```

## 文件结构

```text
graph-ma/
  SKILL.md
  references/
    service-agent.md
    machine-learning.md
    analysis-record.md
    understand-anything.md
  scripts/
    analysis.py
    validate.py
    extract_notebook_outputs.py
  tests/
    test_tools.py
    fixtures/
      service/
      agent/
      notebook/
  agents/
    openai.yaml
  README.md
```

[SKILL.md](SKILL.md) 是技能入口；仅按项目类型读取对应参考文件。[服务与 Agent 检查](references/service-agent.md)覆盖记忆、RAG、路由、工具和回写；[机器学习检查](references/machine-learning.md)覆盖数据、预处理、评估、融合和 Notebook 证据。agents/openai.yaml 提供显示名称、简介和默认提示词。

实际项目解读由宿主 Agent 完成；三个辅助脚本使用 Python 3.10+ 标准库，无第三方依赖，不执行项目业务代码。详细底稿格式、影响范围和更新顺序见 [分析底稿与增量更新](references/analysis-record.md)，可选图谱接入见 [Understand Anything](references/understand-anything.md)。

## 辅助工具

以下命令在被分析项目中执行，`<skill>` 替换为本技能目录。先生成并核实文档与底稿，再记录摘要基线：

```text
python <skill>/scripts/validate.py --document docs/review.md --analysis docs/analysis.json --project . --flowchart docs/assets/main.svg
python <skill>/scripts/analysis.py snapshot --analysis docs/analysis.json --project .
python <skill>/scripts/analysis.py changes --analysis docs/analysis.json --project .
python <skill>/scripts/extract_notebook_outputs.py experiment.ipynb --cells 4,9 --output docs/assets/results
```

校验器也支持只检查文档图片或单独检查底稿。影响报告只覆盖声明的源码范围和依赖；机械校验不证明结论正确，SVG 与结果图仍需可靠渲染并目检。提取的 Notebook 图片标记为历史输出，同名资产拒绝覆盖。

回归测试覆盖服务、Agent 和 Notebook 样例，以及断链、源码删除、依赖影响、输出来源和用户内容保护：

```text
python -m unittest discover -s tests -v
```
