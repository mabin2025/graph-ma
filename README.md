# graph-ma

内置 Understand Anything（UA）式图谱分析，基于真实源码，用简洁流程图、核心代码和真实结果图，生成便于阅读与复盘的中文项目解读。只需调用 graph-ma，即可完成图谱梳理与图文解读。

## 安装与依赖

### 安装 graph-ma

**推荐使用仓库安装脚本：默认同时安装 graph-ma 和 Understand Anything。** 安装前准备 Python 3.10+、Git、Node.js 22+ 和 pnpm 10+；脚本不会替你安装 Python、Node 或包管理器。

Windows PowerShell：

```powershell
git clone https://github.com/mabin2025/graph-ma.git
cd graph-ma
.\install.ps1
```

macOS / Linux：

```bash
git clone https://github.com/mabin2025/graph-ma.git
cd graph-ma
bash ./install.sh
```

安装器会自动下载官方 UA 仓库，在需要时安装其依赖并构建 core，验证解析运行时，然后安装 graph-ma、UA 技能入口及插件定位链接。已有完整、可运行的 UA 环境会复用，不自动拉取或重置其代码；Dashboard 不会自动启动。

默认技能目录为 `$CODEX_HOME/skills`（未设置时为 `~/.codex/skills`），UA 仓库默认位于 `~/.understand-anything/repo`，插件定位链接为 `~/.understand-anything-plugin`。运行后重启宿主，再调用 `$graph-ma`。

已有目标技能与当前版本内容不同时，安装器会停止并提示；显式传入 `-Replace`（PowerShell）或 `--replace`（Bash/Python）后，先把旧目录移入对应目标目录的 `.graph-ma-backups/`，再安装。不会删除这些备份，也不会覆盖已有 UA checkout。

只安装 graph-ma、跳过 UA 时使用 `.\install.ps1 -SkipUA` 或 `bash ./install.sh --skip-ua`；此时安装器只需要 Python 3.10+。自定义位置可使用 PowerShell 的 `-SkillsDir` / `-UADir`，或 Bash/Python 的 `--skills-dir` / `--ua-dir`；其他宿主需选择其支持的技能目录。

也可手动把仓库完整放入技能目录，保留 `SKILL.md`、`references/`、`scripts/` 和 `agents/` 的相对结构。**手动复制文件或通过其他工具安装技能，不会自动执行本仓库安装器，也不会自动安装 UA。**

### 是否需要安装 Understand Anything？

**UA 是运行时可选依赖；推荐安装器默认一并安装。** graph-ma 内置其核心分析方法，不捆绑上游完整源码。

| 使用方式 | 是否需要安装 UA | 其他依赖 |
| --- | --- | --- |
| 由 Agent 梳理源码、建立图谱并生成中文图文解读 | 否 | 支持技能、源码阅读及文件写入的 Agent |
| 读取已有 UA 图谱、运行 graph-ma 的检索与校验脚本 | 否 | 辅助脚本需要 Python 3.10+；Git 时效检查需要 Git |
| 复用 UA 原生扫描、导入映射与符号提取工具 | 是 | 完整 UA 安装及其运行时，按官方说明完成构建 |
| 使用 UA 交互式 Dashboard 和完整上游功能 | 是 | 按 UA 官方说明安装和启动 |

选择跳过 UA 或原生工具不可用时，graph-ma 继续由当前 Agent 分析源码；日常使用技能时不会另行联网安装。只复制 `understand/SKILL.md` 不足以运行 UA 原生解析工具，还需要完整插件及已构建的 core。

### 手动安装 UA（可选）

按照 [UA 官方多平台安装说明](https://github.com/Egonex-AI/Understand-Anything#-multi-platform-installation) 选择对应宿主。官方提供的安装入口如下，安装过程中选择你的平台（例如 `codex`）：

Windows PowerShell：

```powershell
iwr -useb https://raw.githubusercontent.com/Egonex-AI/Understand-Anything/main/install.ps1 | iex
```

macOS / Linux（Codex）：

```bash
curl -fsSL https://raw.githubusercontent.com/Egonex-AI/Understand-Anything/main/install.sh | bash -s codex
```

安装完成后按官方说明重启宿主，并确认插件及运行时可用，再使用 `$graph-ma`。使用 graph-ma 的集成流程不要求事先执行 `$understand`；需要单独使用完整 UA 分析或 Dashboard 时，再按 UA 的工作流操作。运行时版本与构建要求以官方说明为准。

## 适用场景

- 项目接手、架构梳理、调用链和数据流分析。
- Agent、RAG、记忆、规划路由、工具执行和任务调度分析。
- 机器学习与 Notebook 项目的数据、特征、训练评估和融合解读。
- 结合真实项目进行技术学习、项目复盘与面试准备。

## 默认产物

一份 Markdown、一张简洁主图，以及按需选择的子模块 SVG、核心代码片段与真实结果图。图讲流程，代码讲实现，结果图讲观察，正文讲原因与边界；不为每个模块凑齐所有材料。

主图通常保留 4～7 个阶段，子图围绕一个问题展开，详细参数和风险放正文。代码片段说明来源及精简情况，结果图区分历史输出与本次运行。复盘或面试场景可补少量项目相关问答。

事实来源区分源码确认、本地文件实测、历史输出、本次运行、合理推断和待验证。SVG 进行 XML 与渲染检查，结果图检查可读性与来源，Markdown 检查图片链接。默认仅修改指定文档与图形资产，增量编辑保留用户补充，不修改业务代码。

多模块、完整解读或持续维护时，默认在文档目录保存 UA 格式的 `knowledge-graph.json` 和轻量 `analysis.json`。图谱记录文件、关键符号、真实关系、架构分层与阅读路线；底稿把结论、源码位置、章节和图形关联起来，文件摘要检测已提交与未提交的变化，按依赖定位待更新章节。Notebook 分别记录代码与历史输出变化。小范围问题可只在上下文中追踪，不额外落盘。

内置流程是“勘察 → 节点与关系 → 架构分层 → 阅读路线 → 源码核实 → 主图与正文”。没有旧图谱也能直接分析，不必先调用 understand；已有图谱则检查时效、筛选相关子图并补充源码。已安装且可用时，复用 UA 原生扫描和结构解析工具；否则由当前 Agent 完成分析。完整 Dashboard、语义搜索和提交 hooks 未捆绑，交互探索按需使用现有 UA 安装。新增局部图谱保存在文档目录，不覆盖项目原有全量图谱。

## 使用示例

```text
使用 graph-ma 分析当前代码库，生成中文项目解读到指定文档目录。
使用内置 UA 工作流梳理关系、分层和阅读路线，保存当前范围的图谱与分析底稿。
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
  install.ps1
  install.sh
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
    ua_graph.py
    install.py
  tests/
    test_tools.py
    test_ua_graph.py
    test_install.py
    fixtures/
      service/
      agent/
      notebook/
  agents/
    openai.yaml
  README.md
```

[SKILL.md](SKILL.md) 是技能入口；仅按项目类型读取对应参考文件。[服务与 Agent 检查](references/service-agent.md)覆盖记忆、RAG、路由、工具和回写；[机器学习检查](references/machine-learning.md)覆盖数据、预处理、评估、融合和 Notebook 证据。agents/openai.yaml 提供显示名称、简介和默认提示词。

实际项目解读由宿主 Agent 完成；四个分析辅助脚本使用 Python 3.10+ 标准库，无第三方 Python 依赖，不执行项目业务代码。图谱时效检查可使用本地 Git。另有 `scripts/install.py` 供安装入口调用：默认会联网下载 UA 并在必要时运行其依赖安装与构建。详细底稿格式、影响范围和更新顺序见 [分析底稿与增量更新](references/analysis-record.md)，内置流程、原生工具复用及图谱格式见 [Understand Anything 分析](references/understand-anything.md)。

## 辅助工具

以下命令在被分析项目中执行，`<skill>` 替换为本技能目录。先生成并核实文档与底稿，再记录摘要基线：

```text
python <skill>/scripts/validate.py --document docs/review.md --analysis docs/analysis.json --project . --flowchart docs/assets/main.svg
python <skill>/scripts/analysis.py snapshot --analysis docs/analysis.json --project .
python <skill>/scripts/analysis.py changes --analysis docs/analysis.json --project .
python <skill>/scripts/extract_notebook_outputs.py experiment.ipynb --cells 4,9 --output docs/assets/results
python <skill>/scripts/ua_graph.py check --graph docs/knowledge-graph.json --project . --analysis docs/analysis.json
python <skill>/scripts/ua_graph.py query --graph docs/knowledge-graph.json --project . --query 路由 工具 --hops 1 --limit 20
```

校验器也支持只检查文档图片或单独检查底稿。影响报告只覆盖声明的源码范围和依赖；机械校验不证明结论正确，SVG 与结果图仍需可靠渲染并目检。提取的 Notebook 图片标记为历史输出，同名资产拒绝覆盖。

`ua_graph.py` 只读图谱：检查基本结构、节点引用和源码位置，按关键词提取有限子图，并报告项目范围的 Git 变化及可选底稿摘要变化。它不会自动生成图谱、做语义搜索或运行完整 UA 上游流水线；图谱由 Agent 按内置工作流建立。图谱检查以结构错误决定退出码，源码变化另看 `freshness` 和 `analysis_changes`，不能把退出 0 当成图谱最新。

回归测试覆盖服务、Agent 和 Notebook 样例，以及断链、源码删除、依赖影响、输出来源和用户内容保护：

```text
python -m unittest discover -s tests -v
```
