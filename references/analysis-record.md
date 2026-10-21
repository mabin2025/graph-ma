# 可复用分析底稿与增量更新

适用于多模块解读、后续追问和持续维护。一次性的小范围说明可以不生成底稿。底稿放在用户指定的文档目录内，例如 `docs/analysis.json`；只记录已分析的链路，不建立全仓库符号数据库。

## 版本 1 格式

下面是服务项目的格式示意，文件名、行号与结论须替换为目标项目的真实内容。尚未验证时不填写虚假的 `revision`，由验证后的 `snapshot` 命令生成。

```json
{
  "version": 1,
  "scope": {
    "paths": ["src", "config"],
    "exclude": ["src/generated/*"]
  },
  "modules": [
    {
      "id": "request",
      "name": "请求处理",
      "sources": ["src/app.py", "config/app.json"],
      "depends_on": [],
      "sections": ["请求处理：输入怎样到达执行器"],
      "assets": ["assets/main.svg"]
    }
  ],
  "claims": [
    {
      "id": "missing-item",
      "module": "request",
      "text": "记录不存在时返回 404",
      "kind": "source",
      "evidence": [{"path": "src/app.py", "lines": [8, 10]}]
    }
  ]
}
```

- `scope.paths`：相对项目根目录的文件或目录；应包含入口、相关共享代码及配置。排除生成的文档与底稿，避免把自身写入当成源码变化。目录跟踪会发现新文件；只列文件就不能发现旁边新加入的路由。`exclude` 使用区分大小写的 Python `fnmatch` 规则，不支持 gitignore 的反选语法；默认跳过 `.git`、`node_modules`、`.venv`、`__pycache__` 和 UA 图谱目录。
- 所有源码路径用 `/`；`sources` 与 `evidence.path` 相对项目根目录。`assets` 相对底稿目录，置于其子目录。不要存绝对机器路径、密钥或环境变量值。
- `modules[].id` 与 `claims[].id` 全局唯一，更新时尽量保持稳定。`depends_on` 表示“本模块依赖哪些模块”，影响从被依赖模块传播到调用方；循环依赖允许存在。
- `sections` 保存实际文档章节标题；`assets` 保存有关的图形路径。正文与 SVG 可沿用这些模块 ID，方便定位；无需把整段源码复制进 JSON。
- `kind` 为 `source`（源码）、`local`（本地文件实测）、`historical`（历史输出）、`run`（本次运行）、`inference`（合理推断）或 `unverified`（待验证）。前四种必须附证据；本次运行还需指向本次保留的日志或结果，不能仅引用实现代码。
- `evidence.lines` 是包含首尾的 1-based 行范围；Notebook 用 `cell` 表示按文件顺序的 1-based 位置，可同时记录 `cell_id`。Notebook 的 `lines` 指该单元格源码行，非整个 JSON 文件行。保存的图可只指向 Notebook 单元格或结果文件；解释其含义仍需人工核实。
- `revision.files` 由工具生成：以相对路径为键，保存完整文件 SHA-256。Notebook 另存代码与输出摘要；`git_commit` 无 Git 时为 `null`。文件摘要包含未提交修改，不以 commit 相同推断底稿仍然有效。

## 工具用法

以下 `<skill>` 是本技能安装目录，`<project>` 是被分析项目。脚本使用 Python 3.10+ 标准库，无需安装依赖；这些命令并不修改业务源码。

```text
python <skill>/scripts/validate.py --document docs/review.md --analysis docs/analysis.json --project <project> --flowchart docs/assets/main.svg
python <skill>/scripts/analysis.py snapshot --analysis docs/analysis.json --project <project>
python <skill>/scripts/analysis.py changes --analysis docs/analysis.json --project <project>
```

`validate` 可仅传 `--document` 检查图片，或仅传 `--analysis` 和 `--project` 检查证据。生成的流程 SVG 用可重复的 `--flowchart` 参数额外检查 `title/desc`；保留原始历史结果 SVG 时不强制添加描述。外部图片只提示未检查，不发送网络请求。图片链接支持常见内联、引用式和相对路径的 Obsidian 嵌入；依赖全库附件搜索、复杂嵌套 Markdown、HTML/CSS 外部图片的情况需人工检查。

工具以 JSON 报告，机械校验失败退出 1，成功退出 0。`changes` 检出变化仍退出 0，调用者必须读取 `changed_files`，不能仅根据退出码判断内容没变。

## 更新规则

1. 先读取最新文档与底稿，运行 `changes`；此命令只报告，不改文件、不推进基线。
2. 源码新增、修改或删除时，复核关联模块和结论，并沿 `depends_on` 向调用方传播。范围内出现未映射的新文件或配置时，工具保守地要求复核全部已记录模块；必要时重新判断主图。范围之外的变化不会被检测，入口、配置和分析范围调整时必须重新勘察。
3. 重新读当前源码，修订受影响章节、图片及证据，保留用户编辑。行号或 cell ID 改变时重新定位，不删除结论来掩盖检查失败。删除的源码仍会出现在影响报告中。
4. 对照源码复核含义，运行机械校验并渲染目检图片；全部工作完成后才运行 `snapshot` 记录新基线。底稿更新用临时文件原子替换，并在保存前检查内容是否变化；不适用于无锁的多人同时写入，无法安全合并时保留冲突内容。

Notebook 报告的 `code_changed` 与 `outputs_changed` 用于分辨变动来源。代码变了而输出没变，只能说明旧图未更新，不能证明代码运行成功；仅元数据、Markdown 或执行编号变化可能两项都为 false，仍应查看文件差异。

脚本只能验证引用存在、索引结构与摘要变化，不能证明结论正确、真实调用关系完整、程序已运行或 SVG 视觉布局合格。
