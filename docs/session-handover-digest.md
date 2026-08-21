# 会话交接摘要（2026-07-12）

> 本文档补齐「只存在于开发对话中、未落入其他文档」的软信息。新会话（macOS design 工作或 Codex 接管）请按顺序读：项目 `AGENTS.md` → `ROADMAP.md` → README「交接速览」→ 本文档。硬信息（架构、运行方式、数据规则）以那三处为准，此处不重复。

## 1. 三个 demo 的决策状态

| 版式 | 状态 | 定位 |
|---|---|---|
| demo1 卡片流 | 可用 | 方案 A：按 PM 分组卡片流，全量总览 |
| demo2 列表＋详情（分节滚动） | **用户已定稿冻结**，非明确要求不改 | 方案 C 落地：按 PM 分节、左卡片与汇报区等高、卡内列表吸顶 |
| demo3 人名滑动条 | 当前主推，design 迭代都发生在这里 | demo2 基础上改为滑动条切换单 PM 单元＋AI 按钮流程 |

三版共用 `generate_dashboard.py` 数据层——数据规则改一处三版生效，这是刻意设计；版式互不干扰，团队决策后淘汰的模板直接删除即可。

## 2. 设计偏好脉络（design 工作最需要的上下文）

- **去 AI 味是明确诉求**：用户点名要「清爽干净、参考 Notion」。双配色中 Notion 纯白是默认；Claude 暖色（米底＋陶土橙）保留为切换项，但已向用户说明这正是 AI 生成设计的模板味配色、投影仪上米底易发灰——团队演示时让大家自选。
- **投屏是第一场景**：所有字号、对比度决策以会议室投屏可读为准。字号迭代史：详情标题 20→18→15px（用户连续两轮要求缩小）；卡片主体各元素曾整体 +1px；侧栏统一 13px，层级靠粗细不靠字号（TDT 粗体、子任务常规、选中不加粗只用底色＋左线）。用户习惯用「大一号/小两号」表述字号调整。
- **模块化高亮语言**（demo2/3 的右侧详情）：每模块「高亮条（4px 左粗线＋浅底）＋高亮块（3px 左细线＋浅底圆角）」，样式源自 CN6_H581 报告但全部 token 化；风险描述模块与其他模块同色调（曾做过红色特殊化，用户要求撤销），仅正文真实风险文本保持红字。
- **术语**：里程碑第三节点显示 TDR2（不是 KO）；「技术迁移」阶段暂用开发阶段控制点；风险值 空//、暂无、无 一律灰色「/」。
- **正式版 PM 滚轴**：16 人固定相对顺序存 `src/dashboard_config.json` 的 `pm_roster` 键（gitignored）；正式版按 Base 筛选实际命中的 PM 显示，名单外 PM 自动追加，修改配置后重启看板生效。

## 3. 用户协作习惯（本对话中反复验证）

- 视觉类改动先在终端出 ASCII 草稿或对比 Artifact，**确认后再写代码**；小步迭代＋截图反馈是常态。
- 汇报要结论先行、给真实判断（方案有问题直说）；每轮改动即时 commit＋同步 ROADMAP。
- 真实业务数据（Base URL、项目名、人名）一律不入库——本摘要也遵守，具体值见本地 gitignored 文件。

## 4. 跨会话资产：三个 Artifact（claude.ai 账号级，任何设备可访问）

| 内容 | URL |
|---|---|
| 三种形态交互对比页 | https://claude.ai/code/artifact/b8b12811-3763-40a3-82e8-3da75831f9eb |
| 完整看板 demo 预览（双配色） | https://claude.ai/code/artifact/49b948a6-7519-4a55-88b6-e7d741664d04 |
| 架构知识路线图（可勾选进度） | https://claude.ai/code/artifact/09a433ca-682c-4700-87bf-f491f1b1be21 |

在其他设备的 Claude Code 会话中，把 URL 传给 Artifact 工具的 `url` 参数即可**原地更新同一页面**（不会新开链接）。

## 5. 已明确的下一步（按优先级）

1. 团队内部决策 demo1/2/3 版式（用户主持，等反馈）。
2. **design 精修（macOS 上进行）**：可用 DesignSync＋/design-sync 把配色 token 与组件（卡片/徽章/里程碑线/高亮条块/chips）同步到 claude.ai/design 设计系统项目逐个打磨，再回写模板。
3. 平台集成预研：部门项目管理平台加 button→后端直调飞书 OpenAPI（应用身份），业务逻辑层可整体复用，见 architecture-learning-guide 第 2 节。
4. 收录范围扩大（demo 白名单/字段筛选 → 全量进行中子任务）：只改收录逻辑，模板零改动。
5. 2026-07-14 起 Windows 机由 Codex 接管（注意 lark-cli 沙箱提权，README 交接速览有说明）。

## 6. macOS 迁移与环境重建

**打包清单（轻装方案，用户已确认）**：本项目文件夹整包（含 gitignored 的 `src/dashboard_config.json`、`start-dashboard.command`、可选 `output/`）＋ 3 个小文件——工作区根 `AGENTS.md`、根 `CLAUDE.md`（放 mac 工作区根目录），用户级 `~/.claude/CLAUDE.md`（Windows 版拷入 mac 同名路径，内含【仅 Windows】标记条目）。代价：git 历史不随行（决策要点在 ROADMAP），mac 上 `git init` 新起。

**环境重建步骤**：

1. Claude Code 安装并登录**同一 claude.ai 账号**（Artifact 与 Claude Design 项目都挂在账号下）；
2. `chmod +x start-dashboard.command`（zip 打包会丢执行权限，首次必做）；
3. lark-cli 重新 `npm install -g` ＋ `auth login`（凭据不可跨机迁移）；
4. python3、git 就绪（系统自带或 brew）。

**差异速记**：不需要 `python.cmd`/`git.cmd` 包装，直接 `python3`、系统 git；shell 里含 `&` 的 URL 用**单引号**包即可；shell 脚本必须 LF 行尾（`.gitattributes` 已锁定）。

## 7. Claude Design 设计工作流（mac 核心工作）

**原理**：Claude Design 消费「组件库」而非整页 HTML——先拆解、再同步（DesignSync 工具＋ `/design-sync` 命令），形成「Design 环境改 ↔ 模板回写」双向循环。

**四步流程**：

1. **组件化拆解**（一次性）：把 `template-demo3.html` 拆为组件预览（首行 `@dsCard` 标记）——tokens（双配色/深浅色变量）、badge、里程碑线、sec-bar/sec-block 高亮条块、sd-item 侧栏项、chips、ai-btn、pm-unit 整卡布局；
2. **同步上云**：DesignSync 列出/新建设计系统项目（如「TDT 看板设计系统」）→ 确认清单 → 写入；
3. **在 claude.ai/design 迭代**：Design System 面板按组件卡片呈现，自然语言让 AI 改样式或手动调整；
4. **回写代码**：DesignSync 拉回改动组件、对比差异，落回 `template-demo*.html` 的 token/CSS，重新生成看板验证。**纪律：设计探索在 Design 里做，落地以模板文件为准。**

**mac 首次会话可直接粘贴的指令**：

> 读 docs/session-handover-digest.md 和 ROADMAP.md。把 template-demo3.html 拆成组件库（tokens、徽章、里程碑线、高亮条块、侧栏项、chips、AI 按钮、整卡布局），预览一律用虚构示例数据，然后创建 claude.ai/design 设计系统项目并同步上去。

**注意**：组件预览数据必须虚构（真实业务数据不进设计系统）；首次拆解＋同步约半小时量级，之后按组件增量更新是秒级；若 `/design-sync` 命令不可用，直接要求「用 DesignSync 工具同步」等效。
