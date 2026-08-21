# AGENTS.md — 项目状态看板协作规范

## 适用范围

本文件适用于 `projects/01-project-status-dashboard/`。未覆盖事项回退到工作区根目录 `AGENTS.md`。

## 当前阶段

- 正式版 `V1.3.0` 作为本地稳定基线保留，同时进入妙搭全栈迁移阶段：迁移采用本地代码开发，由妙搭服务端统一通过 Base OpenAPI 的独立应用身份只读三个 Base，复用现有业务规则和正式前端，不使用妙搭数据库镜像业务数据。
- 迁移仍归当前业务 Project 管理；妙搭源码位于 `deployments/miaoda-app/`，由其独立 Git 仓库和妙搭远端 `sprint/default` 管理，父 Git 必须忽略该目录。父 Git 只保存方案、规范、`ROADMAP.md`、本地 `V1.3.0` 和 `deployments/miaoda-app.json` 版本档案。
- 妙搭迁移固定方案为 `docs/miaoda-full-stack-migration-solution.md`；开发期应用保持仅创建者可见，不添加协作者或其他操作者，团队试点延后至用户另行授权。
- 当前唯一正式模板为 `src/template-dashboard-v1.3.0.html`；`src/template-dashboard-v1.0.0.html`、`src/template-dashboard-v1.1.0.html` 与 `src/template-dashboard-v1.2.0.html` 仅保留为旧版本兼容文件，Demo1～3 保持冻结，不再继续迭代。
- 正式版通过 `--filter-field "是否上周三例会"` 从 Base 动态收录子任务；`src/dashboard_config.json` 只保存 PM 固定相对顺序，不再混入 Demo 白名单或创新大赛本地数据。旧 `--scope` 白名单仅作为非正式兼容入口保留。
- 遗留问题固定以生成日期所在的 ISO 周为本周锚点，并以日期减 7 天得到上一 ISO 周；只展示这两个标准周次的内容，不得再从 Base 记录反推“最新周”，也不得用周数直接减 1 处理跨年。
- 会议纪律属于数据内容，不得硬编码在正式 HTML 模板中。本地 `V1.3.0` 以 `src/meeting_content.json` 为正式内容源，妙搭版以 App 仓库 `shared/meeting-content.ts` 保存同构内容；两端均通过 `DATA.meetingDiscipline` 渲染，并保持正式文案一致。
- 正式看板版本遵循 SemVer：不兼容的契约变化升级主版本，向后兼容的功能或业务规则升级次版本，仅修复既有实现且不改变契约时升级补丁版本。每次升级必须新建正式模板并保留上一版回退文件，同时同步本地与妙搭入口、测试、README 和 `ROADMAP.md`。
- `V1.3.0` 的本周新增口径固定为：项目概况第一张柱状图的概述以生成日期所在的 ISO 周为本周，按子任务记录系统创建时间统计本周新增。存在新增时追加“本周新增X个，其中硬件系统X个，AIX个。”，赛道分项沿用 Base 选项顺序且不重复“赛道”二字；不存在新增时不追加。新增总数包含赛道空值记录，但汇报句只列非空赛道；赛道空值不得写成“未填写赛道X个”进入汇报句，须在同一卡片中以独立数据质量警告显示数量及项目编码／名称，全部赛道为空时汇报句只保留“本周新增X个。”。系统创建时间缺失或无法解析时不得猜测为本周新增，须输出可见警告。
- 每次功能或样式修改后都要核对 `start-dashboard.cmd` 与 `start-dashboard.example.cmd`：启动参数或启动逻辑变化时同步修改两份脚本；参数未变化时无需机械改写，但必须验证双击入口能够加载最新代码。两份 `.cmd` 必须保持 CRLF 行尾。
- 本地看板服务固定使用项目身份 `tdt-project-status-dashboard` 和默认端口段 `8710—8719`；8765已被不同项目历史共用并产生浏览器旧页面残留，不再作为默认入口。健康接口必须返回项目身份与当前源码构建标识，启动URL必须携带当前构建标识以强制浏览器重新导航。启动脚本只允许复用身份和构建均匹配的服务，不得占用或终止其他项目的本地服务。显式 `--port` 用于临时验证时继续尊重用户指定值。
- 每次开始工作前先读取本文件、`README.md` 和 `ROADMAP.md`。

## 视觉规范

- 项目根目录 `design.md` 是正式视觉规范的唯一来源；修改 `src/template-dashboard-v1.3.0.html` 的布局、颜色、字体、表格或图表前必须先读取。规范内调整直接实施；超出规范的视觉决策先更新 `design.md`，再改模板。
- 正式模板只使用其 `:root` 中的统一视觉 token，不引入外部字体、前端依赖或第二套近似颜色。表格表头和正文统一由 `--table-font-size: 16px`、`--table-head-weight: 700`、`--table-body-weight: 400` 控制。
- 项目概况的两张计数柱状图均须保留纵轴刻度和横向网格，纵轴从 0 起；`chartScale()` 的最小步长固定为 1，不能为低计数显示小于 1 的小数刻度。
- 视觉改动不得改变 Base 字段映射、`/api/data` 刷新协议、离线单文件导出或 `DATA.meetingDiscipline` 中的会议纪律正式文案；静态文案不属于视觉替换范围。
- 每次视觉模板改动至少运行 `node tests/test_empty_table_cells.mjs`、`node tests/test_template_refresh.mjs`、`node tests/test_template_design.mjs` 与 Python 运行时回归；需要验证真实数据时，再通过正式启动入口加载页面。

## 数据与安全

- 进展、问题与创新大赛 Base URL 运行时分别通过 `--base-url`、`--issue-base-url`、`--innovation-base-url` 传入，不硬编码进代码、文档或 Git。
- 本地 `V1.3.0` 凭据继续依赖 lark-cli 本机登录态；妙搭版改用 Base OpenAPI 的独立应用身份，目标 Base 须单独授予该应用足够的文档／高级权限。两种链路的 token、app secret、环境变量值均不得写入代码、文档、日志或 Git；三个 Base URL 只允许保存在妙搭环境变量和已忽略的本地 `.env.local`。
- 看板生成与刷新链路只读 Base 数据，不提供填写或回写能力；团队成员必须在对应 Base 数据源维护内容，再通过「重新生成」刷新看板。
- 正式看板启动时首次抓取成功，以及页面内每次「重新生成」成功后，都必须同步输出可离线转发的单文件 HTML：按生成日期与两位 ISO 周次写入 `output/YYYY-MM-DD(WXX)-TDT技术项目状态看板.html`；同一天覆盖当天文件，跨日期创建新文件并保留历史文件。
- 上一条自动写入规则只适用于本地 `V1.3.0`；妙搭迁移版提供由用户主动触发的自包含 HTML 下载，不在妙搭服务端永久存储真实业务快照。
- 项目级 Skill `siyuan-refresh-tdt-stage-snapshot` 暂停使用；阶段快照相关维护暂由部门专人手工处理，任何 Agent 均不得运行该 Skill 的预检或写入脚本。
- 总表已移除「阶段快照日期」字段；看板生成与刷新链路不得依赖该字段，也不得隐式调用阶段快照维护脚本。后续如重新启用该 Skill，须先在目标总表中增加「阶段快照日期」字段。
- 真实项目数据不入库：`output/`（生成的看板 HTML）与 `src/dashboard_config.json`（正式 PM 顺序配置）已列入 `.gitignore`；旧兼容白名单 `src/demo_scope.json` 如存在也继续忽略，新增含真实数据的文件必须同步排除。

## Base 映射总原则

- 在看板已纳入范围的记录和已映射字段内，Base 是唯一业务事实来源：`null`、空字符串和纯空白显示为空白；其他任何非空值，包括 `/`、`／`、各类横线及「未填写／暂无／无」，都必须在看板中留下可见、可追溯的呈现，不得作为占位符静默清除。
- 允许对 Base 值进行不改变业务含义的格式化、徽章化、拆分、排序、分组、聚合和已确认的归一化，例如将 `NOTE70` 归一为 `NOTE`；转换规则必须明确、可验证，且不得脱离 Base 原始数据补数或把非空值变为空白。
- 稳妥边界是“已纳入范围的记录＋已映射字段”，不是无条件展示 Base 的每个字段和全部历史内容。记录筛选、时间范围、最新日期块截取、字段别名回退和聚合口径等有损规则必须在 `README.md` 的字段映射中显式说明；未修改对应业务规则时，不得借映射调整顺手改变其范围。
- 合法日期等结构化值可以转换为看板格式；无法解析的非空值必须保留原文并输出警告。UI 空状态或诊断提示必须与业务字段展示区分，不得伪装成 Base 输入。
- “本周新增”只读取 Base 记录系统字段 `created_time`，不得用最后修改时间、阶段对比结果或业务字段日期代替。本地链路通过已登录的 lark-cli 用户身份调用官方查询记录接口并显式请求 `automatic_fields=true`；妙搭链路使用既有独立应用身份请求同一字段。时间戳统一转换为 `Asia/Shanghai` 后再与生成日期的 ISO 周比较。
- 本节规则不得只停留在 `AGENTS.md`：生成脚本的中央取值函数、正式模板的中央渲染函数和对应自动化测试必须同步体现，使规则随可运行资产一起迁移；修改其中一层时必须核对另外两层。
- 固定赛道数、PM 空值归组等独立业务规则即使与总原则存在潜在张力，也必须先说明影响并取得确认后再修改；不得在其他映射修复中一并改动。

## 文档维护

- 稳定的项目目标与使用方式写入 `README.md`。
- 阶段、进度、阻塞和验证结果写入 `ROADMAP.md`。
- 需求或技术路线改变时，先同步受影响的规范和文档，再实施代码改动。
- 跨项目复用的“本地全栈开发 → App Git → 妙搭发布 → 线上验收”规则统一维护在项目根目录 `MIAODA_LOCAL_TO_ONLINE_RULES.md`；后续新 Project 采用同类链路时，必须先复制或引用该规则，再补项目特有约束，不得重新从零摸索。

## 妙搭部署门禁

- 本地 lint、类型检查、单元测试和 `npm run build` 成功，只能证明本地代码与构建过程可运行，不能单独证明妙搭可部署。App 每次涉及构建脚本、运行入口、平台脚手架或依赖升级时，必须对照当前妙搭官方脚手架确认部署产物契约，并自动检查 `dist/run.sh`、`dist/package.json`、`dist/server/main.js`、`dist/node_modules/` 和 `dist/dist/client/index.html` 均位于妙搭运行时约定的位置；缺少任一项均不得 push 或发布。
- 妙搭发布验证必须分成“应用产物”和“平台运行环境”两层。应用产物门禁通过后，仍须以 `release-get` 返回 `finished`，并完成线上首页、`GET /api/data`、重新生成和离线下载冒烟验收，才能标记发布完成。TrustLayer、平台内部 DNS、网关或 FaaS 等平台错误必须与应用缺陷分别记录；本地修复不得宣称解决平台故障，只能通过新的 release 复核平台异常是否仍存在。失败时记录非敏感的 release ID、失败步骤和关键错误，禁止无差别连续重试。

## 妙搭双仓库规则

- 父 Git 禁止跟踪 `deployments/miaoda-app/`；不得使用 `git add -f` 绕过忽略规则，不得删除 App 的 `.git` 后继续提交。
- App 源码操作统一使用 `git -C deployments\miaoda-app ...`，提交前必须以 `rev-parse --show-toplevel` 确认命中 App 仓库。
- App 开发分支固定为 `sprint/default`；禁止直推 `main`，禁止 force-push。发布成功后由妙搭服务端推进发布态 `main`。
- 每次 App 验证或发布后，必须同步更新父 Git 中的 `deployments/miaoda-app.json` 和 `ROADMAP.md`，记录非敏感的 App commit SHA、release ID 和验证状态。
- App 仓库初始化后必须先读取其 `.agents/skills/plugin-guide/SKILL.md`；如仓库内存在更具体的 `AGENTS.md`，以其规则为准。
