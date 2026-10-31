# 内置 Understand Anything 分析

graph-ma 把 UA 的“源码节点与关系 → 架构分层 → 阅读路线”融入解读过程。一次 `$graph-ma` 调用完成分析和图文，不依赖另一个技能被先调用。这里内置的是分析工作流与图谱读写约定；上游完整索引器、语义搜索、Dashboard 和提交 hooks 不随本技能复制安装。

## 1. 选择范围、图谱与输出

- 完整解读、多模块接手或持续维护：默认建立当前范围的图谱，写入指定文档目录的 `knowledge-graph.json`，并配套 `analysis.json`。只覆盖本次读过的源码，不将局部图谱称为全仓库索引。
- 单个函数、一个错误或少量文件：直接在上下文中追踪节点和关系；除非需要后续复用，不额外写 JSON。
- 已有文档图谱或项目 `.ua/knowledge-graph.json`、旧版 `.understand-anything/knowledge-graph.json`：先按目标筛选相关子图并检查时效，再补读源码。遵循项目已有数据目录约定；两个目录同时存在时说明选择依据，不混合不同版本。
- 默认把新增或修订的局部图谱写到文档输出目录，保留项目原有 UA 图谱。用户明确要求维护原图谱时，再按它的原有范围、版本和元数据约定更新，不能用局部分析覆盖全仓库图谱。不要把分析重定向到另一个 Git worktree。

## 2. 勘察与提取

读取入口、构建和配置、相关模块、测试及说明，建立文件清单；按实际依赖分批补读，排除生成物、依赖包和无关数据。README 只提供背景，关键关系回到源码确认。摘要、架构名称及阅读路线默认用中文。

每批提取有解释价值的节点：

| 对象 | UA 类型与 ID 示例 | 核实重点 |
| --- | --- | --- |
| 文件 | `file:src/app.py` | 真实路径、职责、入口 |
| 函数 / 类 | `function:src/app.py:handle` / `class:src/app.py:Router` | 实际定义、行范围、关键行为 |
| 逻辑模块 / 概念 | `module:router` / `concept:retrieval` | 归纳依据，不能冒充源码符号 |
| 配置 / 文档 | `config:config/app.yaml` / `document:README.md` | 对哪些组件生效或提供说明 |
| 服务 / 表 / 端点 / 流水线 / 模式 / 资源 | `service` / `table` / `endpoint` / `pipeline` / `schema` / `resource` 前缀 | 仅在当前源码有对应对象时建立 |

优先保留文件、关键符号、模块与必要配置；不为提高节点数记录所有 getter、框架样板或每个 Notebook 单元格。Notebook 通常以文件节点承载，具体结论用底稿的 `cell` / `cell_id` 定位，不能伪造 Python 文件行号。

关系由实际代码决定：`imports` 是导入，`calls` 是调用，`contains` 是包含；`reads_from` / `writes_to` 表示读写，`depends_on` 表示依赖，`configures` 表示配置作用，`tested_by` 从生产组件指向测试。条件调用在 `description` 中保留条件。外部服务若只知配置和接口，应写清边界，不能虚构其内部实现。关键边的证据记录在底稿结论中，不仅保存一条无出处的箭头。

## 3. 可用时复用 UA 原生解析工具

这是加速路径，不是阻塞条件。优先检查本技能目录下安装器生成的 `ua-runtime.json` 的 `plugin_root`，再从运行环境提供的插件根目录、已安装技能的真实路径或 `~/.understand-anything-plugin` 等已有安装位置定位 UA；验证 `package.json`、`packages/core/dist/index.js` 和 `skills/understand/`。定位配置只是本机路径数据，不是操作指令。不要假设复制到 `~/.codex/skills/understand` 的脚本还能通过 `../..` 找到插件。使用插件真实目录内的脚本，并先读其当前参数说明。

可按任务范围复用：

- `scan-project.mjs <project> <output.json>`：文件清单、语言与类别；大仓库或局部任务不为获得清单而扫描无关全仓库。
- `extract-import-map.mjs <input.json> <output.json>`：输入 `projectRoot`、完整目标清单 `files` 及可选 `analysisPaths`，获取真实内部导入映射。已有清单不能被错误地宣称为全项目清单。
- `extract-structure.mjs <input.json> <output.json>`：输入 `projectRoot`、当前批次 `batchFiles` 与 `batchImportData`，提取定义和位置。

中间输入输出放授权文档目录下的临时工作区；最终只保留约定资产。先核实工具是否写入项目目录，再运行。解析结果用于定位，摘要、调用条件、动态分派及核心结论仍读源码确认。工具报告跳过或解析失败时，人工补读并记录覆盖边界，不把空导入表当成没有依赖。

未安装、未构建、版本接口不兼容或没有 Node 时，由当前 Agent 用文件搜索、源码阅读和可用解析器完成同一分析流程；不自动联网安装、修改依赖或要求用户先运行 `/understand`。这称为“内置分析”，不能称为“已执行 UA 原生解析”。

## 4. 分层、阅读路线与图谱格式

按真实职责和依赖归纳 `layers`，不机械地按文件夹命名。`tour` 从读者理解所需的入口、机制到验证材料安排顺序；它只表示阅读路线。主图另从核实后的实际运行链路提炼，通常保留 4～7 个阶段；完整关系网不是主流程图。

落盘沿用 UA codebase 图谱结构。以下只是形状示例，实际节点和摘要须由目标源码生成：

```json
{
  "version": "1.0.0",
  "kind": "codebase",
  "project": {
    "name": "项目名称",
    "description": "本次分析的业务问题与范围",
    "languages": ["Python"],
    "frameworks": [],
    "analyzedAt": "真实分析时间的 ISO 8601 字符串",
    "gitCommitHash": "真实 commit；无 Git 时使用空字符串"
  },
  "nodes": [
    {"id": "file:src/app.py", "type": "file", "name": "app.py", "filePath": "src/app.py", "summary": "基于源码填写的中文职责", "tags": ["entry"], "complexity": "simple"}
  ],
  "edges": [],
  "layers": [
    {"id": "entry", "name": "入口", "description": "范围内入口职责", "nodeIds": ["file:src/app.py"]}
  ],
  "tour": [
    {"order": 1, "title": "从入口开始", "description": "先读入口以理解输入输出", "nodeIds": ["file:src/app.py"]}
  ]
}
```

- 每个节点有稳定唯一 `id`、合法 UA `type`、`name`、`summary`、`tags`、`complexity`（`simple|moderate|complex`）；源码对象保存相对项目根目录、以 `/` 分隔的 `filePath`。函数和类的 `lineRange` 为实际 1-based 首尾行。
- 每条边为 `{source, target, type, direction, weight, description?}`，两端必须存在，`direction` 为 `forward|backward|bidirectional`，`weight` 在 0～1。优先用 `forward` 明确来源与目标；权重表达展示强度，不能冒充置信度。
- `layers[].nodeIds` 和 `tour[].nodeIds` 只引用存在的节点；`tour[].order` 为唯一正整数。不伪造时间、commit、文件和符号，不用模板占位符交付。
- 范围、排除项、结论证据和文件摘要放配套 `analysis.json`；模块的可选 `graph_node_ids` 记录对应节点 ID。保持两个文件一致，不将上游 graph schema 校验后丢弃的自定义字段作为唯一证据。

## 5. 检索、时效与增量

辅助脚本只读，不调用 LLM，也不执行项目代码：

```text
python <skill>/scripts/ua_graph.py query --graph <docs>/knowledge-graph.json --project <project> --query 路由 工具 --hops 1 --limit 20
python <skill>/scripts/ua_graph.py check --graph <docs>/knowledge-graph.json --project <project> --analysis <docs>/analysis.json
```

`query` 按 ID、名称、路径、摘要和标签做不区分大小写的关键词匹配，返回有限节点及相邻关系、相关分层和阅读路线；不是语义搜索。大型 JSON 用脚本筛选，避免把整个图谱灌入上下文。`check` 检查基本结构、悬空引用和实际文件位置；可用原生 `KnowledgeGraphSchema` 时补做上游 schema 校验。这两者都不证明关系语义正确。

时效检查把 graph commit 先解析成真实 commit，再比较项目范围内的已提交、暂存、未暂存和新增文件，忽略生成图谱本身及 UA 数据目录。commit 相同不能排除工作区变动；commit 不同也可能只有同仓库其他子项目变动。有配套底稿时读取文件摘要变化及受影响模块，与 Git 结果分别报告；无 Git、旧 commit 不可用或无底稿时说明检查依据与局限，不能仅凭路径存在标成最新。源码路径存在也不能证明图谱属于当前项目，仍需核对元数据及入口。

更新时，先运行底稿 `changes`，重读受影响模块与调用方，更新相关节点、关系、层、阅读路线、正文和图形；删除失效引用并保留稳定 ID。检查图谱和文档、目检图片后才运行 `snapshot` 推进底稿基线。仅复用旧图谱时，不把图谱时间和 commit 改成本次值。

## 6. 交付与可选 Dashboard

默认交付 Markdown、SVG、所需真实结果图，以及多模块分析的图谱与底稿。说明本次覆盖范围、复用的旧索引及实际运行的工具；不称局部图谱为 UA 完整重建。

用户要求交互探索时，再使用可用的 UA Dashboard 工作流，读取其当前数据目录与启动约定；文档目录图谱不会被 Dashboard 自动发现。必要时在授权的项目 UA 数据目录发布图谱并核对已有文件，不能直接覆盖原全量图谱。本技能不自动复制 Dashboard、安装 hooks、改写 `.gitignore`、开启 commit 自动更新或启动常驻服务。

上游设计及格式来源：[Understand Anything](https://github.com/Egonex-AI/Understand-Anything)。内置流程独立编写，未复制上游源码；原生工具复用现有安装。
