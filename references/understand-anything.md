# 按需复用 Understand Anything

项目已有 `.ua/knowledge-graph.json` 或旧的 `.understand-anything/knowledge-graph.json` 时读取本文件。没有图谱时直接沿源码分析，无需安装工具或先做全仓库索引。

## 作为导航索引使用

1. 确认图谱属于当前项目，读取 `project` 元数据和 `gitCommitHash`，再按目标问题筛选 `nodes`、相关 `edges`、`layers` 与 `tour`，避免把完整图谱灌入上下文。
2. 检查索引时效：将图谱 commit 验证为真实 commit 后，比较该版本与当前 HEAD 的项目范围差异，并检查暂存、未暂存和新增文件。单纯 commit 不同不能说明所选子项目变化；commit 相同也不能排除工作区变化。不要把用户提供的 hash 直接拼入 shell 命令。
3. 无 Git、commit 不可用或范围不明时，把索引视为待核实的定位线索。对命中的入口、关键分支、配置与存储回到当前源码核实；节点摘要和 `calls` 边本身不能替代源码证据。
4. 从 `layers` 辅助归纳职责，从相关节点和关系中提取主链路；选择 `tour` 中适合当前读者的阅读顺序。保留实际分支，不能把图谱的展示顺序当成运行顺序。

## 写入 graph-ma 底稿

只摘取当前解读所需的模块、真实关系与来源，转换为 [analysis-record.md](analysis-record.md) 的格式。原图谱节点 ID 可辅助建立对应关系，但正文中的模块名称与 ID 应在本次文档内一致。需要补充图谱没有表达的代码行、Notebook 单元格、配置条件与结果来源。

不自动修改 UA 图谱、安装 hooks、启动 Dashboard 或扩大分析范围。用户要求更新图谱时再按可用的 UA 工作流处理；graph-ma 本身只交付约定文档与支撑资产。
