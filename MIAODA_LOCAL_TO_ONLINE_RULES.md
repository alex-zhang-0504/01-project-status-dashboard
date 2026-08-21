# 妙搭全栈应用：本地开发到线上发布通用规则

## 适用范围

本文件沉淀从本地创建或维护妙搭全栈应用、提交到妙搭 Git、发布到线上并验收的通用流程。新 Project 采用“本地代码开发＋妙搭托管”时，应先复制或引用本规则，再结合项目自身的数据、权限和验收口径补充项目级 `AGENTS.md`。

本文件只记录可跨项目复用的工程规则。具体 App ID、Base URL、凭据、人员、业务字段和真实数据不得写入本文件。

## 一、先确定四个边界

1. **开发方式**：需要本地 IDE／Agent 维护源码时，选择妙搭本地全栈，不与妙搭云端 AI 同时修改同一分支。
2. **仓库边界**：业务父项目和妙搭 App 使用两个独立 Git 仓库；父仓库保存方案、规则、进度和 App 版本指针，App 仓库保存可部署源码。
3. **数据边界**：敏感凭据和真实数据坐标只进入本地 `.env.local` 或妙搭环境变量，不进入代码、文档、日志和 Git。
4. **完成边界**：本地测试通过、代码 push 成功、release `finished` 和线上功能验收是四个不同状态，缺一不可。

## 二、推荐目录与双仓库结构

```text
project-root/
├─ AGENTS.md
├─ README.md
├─ ROADMAP.md
├─ deployments/
│  ├─ miaoda-app.json       # 非敏感版本指针
│  └─ miaoda-app/           # 独立 App Git，父 Git 必须忽略
└─ MIAODA_LOCAL_TO_ONLINE_RULES.md
```

必须遵守：

- 父仓库 `.gitignore` 忽略整个 `deployments/miaoda-app/`，不得用 `git add -f` 绕过，也不得删除 App 的 `.git` 后交给父仓库管理。
- App 操作统一使用 `git -C deployments\miaoda-app ...`；提交前运行 `git -C deployments\miaoda-app rev-parse --show-toplevel`，确认没有命中父仓库。
- App 日常分支固定为 `sprint/default`；`main` 是妙搭发布态，不直推、不 force-push、不改写历史。
- `deployments/miaoda-app.json` 只记录 App ID、开发分支、最近验证 commit、release ID 和验证状态，不记录 URL、secret 或业务数据。

## 三、初始化与本地开发

### 3.1 新建或接入 App

标准顺序：

```text
确认 full_stack 与本地开发
→ 创建或解析 app_id
→ 初始化 App 独立仓库
→ 切到 sprint/default
→ 阅读 App 的 AGENTS.md 与 .agents/skills/plugin-guide/SKILL.md
→ 拉取／配置本地环境变量
→ 安装依赖并启动
```

规则：

- `app_...` 是妙搭 App ID；`cli_...` 是飞书应用 ID，不能混用。
- Git 凭据优先由 `lark-cli apps +init` 或 `+git-credential-init` 配置，不在弹窗中填写普通飞书账号密码。
- 初始化后先保留官方脚手架，再迁移业务代码。不要用本地项目的 `package.json`、启动脚本或目录结构整体覆盖妙搭模板。
- 本地与妙搭云端 AI 不得同时改同一 `sprint/default`。需要云端任务前先确认分支已同步且工作区无未提交的相关改动；云端任务结束后先 fetch／diff，再继续本地开发。

### 3.2 环境变量

- 本地使用被 Git 忽略的 `.env.local`；只提交没有真实值的 `.env.example`。
- 妙搭 `dev` 与 `online` 环境分别配置并逐项回读 key 是否齐全，汇报时只写 key，不回显 value。
- Secret、token 和真实 Base URL 只由服务端读取，禁止进入前端 bundle。
- **修改 online 环境变量不会自动更新已运行实例中的进程环境。** 环境变量切换后必须创建新 release，并通过线上实际数据重新验收；否则页面可能仍读取旧数据源。
- 换成专用只读飞书应用时，只替换 App ID／Secret 并重新发布、复验；使用者不需要各自申请飞书应用，服务端统一使用部署凭据读取数据。

## 四、飞书 Base 接入规则

- 先用副本完成开发和数据契约验证，再只替换环境变量切换正式 Base；不为正式切换修改业务代码。
- 当妙搭多维表格插件不能读取 Lookup／公式等必需字段时，改用服务端 Base OpenAPI，不要接受字段缺失的降级结果。
- Base OpenAPI 调用只保留鉴权、字段／视图查询和记录读取；只读应用禁止新增、更新或删除记录。
- 应用权限和 Base 文档权限是两层：飞书应用具备 API scope，不等于能读取目标 Base。开启高级权限的 Base 还需把文档应用加入目标 Base 并授予满足读取要求的权限；以实际 API 读取为准。
- 妙搭应用可见范围、妙搭协作者权限和 Base 数据权限是三套独立机制，不得互相替代。
- Lookup／公式字段必须使用真实副本和正式表分别抽样验证；不能只根据字段设置页是否可勾选判断 OpenAPI 可读性。

## 五、平台脚手架与部署产物契约

### 5.1 官方模板是部署契约来源

涉及以下内容时，先与当前妙搭官方全栈模板逐文件对比，再一次性合并差异：

- `package.json` 的构建、`prepare`、`postinstall`、`upgrade` 等脚本；
- `package-lock.json` 和平台依赖；
- 开发启动与保活脚本；
- `run.sh`、服务端入口和客户端产物目录；
- Git hooks 和 Windows／Linux 兼容入口。

不得让云端 AI 通过“删除 `package-lock.json`”或只移除冲突标记来掩盖脚手架冲突。正确做法是先确定最终 `package.json`，再重新生成 lockfile，并运行完整门禁。

### 5.2 强制部署产物

每次构建后必须自动确认以下路径同时存在：

```text
dist/run.sh
dist/package.json
dist/server/main.js
dist/node_modules/
dist/dist/client/index.html
```

缺少任一项均不得 push 或发布。`npm run build` 成功只能证明构建命令返回成功，不能证明妙搭运行时能找到入口。

平台脚本兼容要求：

- `run.sh` 使用 LF，并保留 Git 可执行位；从部署根目录启动 `server/main.js`。
- Windows `.cmd`／`.bat` 使用 CRLF，并用全新 `cmd.exe` 模拟双击验证。
- Windows Git hook 或脚手架调用 npm 时，应使用 Node 可正确启动的 Windows npm CLI 入口；不得用 `--no-verify` 绕过 hook。

## 六、Git、Push 与妙搭云端联动

### 6.1 发布前 Git 顺序

```text
git status／diff
→ 本次相关文件 add
→ commit
→ push origin sprint/default
→ 核对远端 SHA
→ release-create
```

`release-create` 部署的是远端 `sprint/default`，不是本地工作区。未 commit、未 push 的文件不会进入发布。

### 6.2 冲突处理规则

- push 前先 fetch 并比较本地与远端；远端有新提交时，查明来源后再整合。
- 本地和妙搭云端 AI 同时改同一分支，是冲突的高风险来源；一个阶段只能有一个写入者。
- 非 fast-forward 时先停止发布；取得用户对 rebase 的明确授权后，才可执行 `git pull --rebase origin sprint/default` 并人工解决冲突。禁止 force-push。
- 出现未合并文件时，先用 `git status` 和冲突标记清单确认范围，不继续 pull、build 或 release。
- `merge --abort`、`reset --hard` 等恢复操作可能丢失工作区内容，必须按项目红线单独确认；执行前先确认目标仓库、目标分支、远端 SHA 和可恢复性。
- 云端 AI 给出的“已修复”结论必须回到本地 Git 状态、文件内容和门禁验证，不以对话回复替代证据。

## 七、发布门禁与完成标准

### 7.1 本地门禁

提交与 push 前至少完成：

```text
npm run verify:release
→ lint
→ 服务端／客户端类型检查
→ 生产构建
→ 自动化测试
→ 五类部署产物存在性检查
```

同时运行：

- `git diff --check`；
- 敏感值扫描；
- 关键运行入口的行尾／可执行位检查；
- 本地首页、数据接口、重新生成和离线下载回归。

### 7.2 发布门禁

1. `git push origin sprint/default` 成功，远端 SHA 与待发布 SHA 一致。
2. `lark-cli apps +release-create --app-id <app_id> --branch sprint/default --as user` 返回 release ID。
3. 每 20 秒用 `+release-get` 轮询；只有同一 release 返回 `finished` 才算部署完成。
4. 核对 `release-get.commit_id` 与预期 App commit 一致，并保存非敏感 release ID。
5. 在登录态浏览器完成线上首页、数据接口、首次生成／重新生成和离线下载冒烟验收。
6. 离线产物检查数据占位符已替换、关键业务统计正确，且没有意外外链资源。
7. 查询发布后时间窗内 ERROR／WARN 日志；按需查询 requests、latency、CPU 和 memory。观测接口没有采样点时，只能写“未返回采样”，不能写“性能正常”。

## 八、应用缺陷与平台故障分层

排障时按两层记录证据：

| 层级 | 典型证据 | 处理原则 |
|---|---|---|
| 应用产物 | 文件缺失、入口错误、依赖缺失、类型／测试失败 | 修代码或构建配置，重新通过本地门禁 |
| 平台运行环境 | TrustLayer、内部 DNS、网关、FaaS、发布基础设施错误 | 记录 release ID、步骤和非敏感错误；应用修复不能宣称解决平台故障，只能通过新 release 复核 |

禁止无差别连续重试。平台故障出现时，先确认应用产物门禁已通过，再用新 release 判断平台异常是否仍存在。

浏览器控制台中的旧静态资源错误不能直接代表当前 release 异常；必须核对错误时间、静态资源 commit、页面最新生成时间和妙搭线上日志。

## 九、本次迁移踩坑与强制预防

| 走过的弯路 | 根因 | 后续强制规则 |
|---|---|---|
| 本地测试通过，但妙搭启动找不到入口 | 本地构建输出与妙搭部署目录契约不一致 | 自动检查五类 `dist` 产物；缺一项禁止 push／release |
| 误把 DNS／502 当成业务代码错误 | 平台运行环境与应用产物没有分层 | 先过产物门禁，再用 release 和平台日志判断；不靠本地修复宣称平台恢复 |
| 妙搭开发页出现多个未合并文件 | 本地 push 与云端 AI 在同一分支并发修改 | 同一阶段只允许一个写入者；云端任务前后必须同步 Git 状态 |
| `package.json` 冲突导致构建系统无法启动 | 平台脚手架脚本被业务版本覆盖 | 对照官方模板逐项合并脚本；最终 `package.json` 确认后重建 lockfile |
| 删除 lockfile 被当作冲突修复 | 只消除了表象，没有固定依赖契约 | 不删除 lockfile 规避问题；重建并验证后提交 |
| 本地环境变量已换正式表，线上仍读旧表 | 旧 release 的进程环境没有重启 | online 环境变量变更后必须新建 release，并用业务统计确认数据源 |
| 插件页无法勾选 Lookup 字段 | 插件能力不覆盖必需字段 | 先验证字段契约；不满足时统一走服务端 Base OpenAPI |
| 应用已有 API scope 仍读不到正式 Base | 缺少目标 Base 文档级权限 | 在 Base 高级权限中加入文档应用并实测读取 |
| Git 凭据弹出普通用户名／密码框 | 未通过妙搭凭据初始化访问远端 | 使用 `+init` 或 `+git-credential-init`，不填写个人飞书密码 |
| 父仓库可能误收 App 源码 | 嵌套 Git 边界不清 | 父仓库忽略 App 目录，App 命令统一 `git -C` 并核对顶层目录 |
| `release-create` 成功就被当成上线完成 | 发布只是进入异步队列 | 必须等同一 release `finished`，再完成线上四项冒烟 |

## 十、归档与交接

每次 App 验证或发布后，同步更新父项目：

- `ROADMAP.md`：完成项、阻塞、release ID、commit SHA、验证范围和异常日志结论；
- `deployments/miaoda-app.json`：最近验证 commit、release ID、状态；
- `README.md`：只维护稳定的使用方式和权限边界；
- App 仓库自身文档：记录稳定架构与环境变量 key，不记录真实值。

提交必须分别进行：先提交／push App Git，再提交父 Git 的规则和版本档案。父 Git 提交时只暂存当前项目路径，避免扫入工作区其他 Project 的未跟踪文件。

## 十一、可复制验收清单

- [ ] 已确认 `app_id`、App 仓库顶层和 `sprint/default`。
- [ ] 已读取 App `AGENTS.md` 与平台 Skill。
- [ ] 本地、dev、online 环境变量 key 齐全，真实值未入库。
- [ ] Base 应用权限和文档权限均以真实只读调用验证。
- [ ] 云端 AI 与本地开发没有并发写同一分支。
- [ ] `npm run verify:release` 全部通过。
- [ ] 五类 `dist` 部署产物全部存在。
- [ ] 本次相关改动已 commit 并 push，远端 SHA 已核对。
- [ ] release 返回 `finished`，commit ID 与预期一致。
- [ ] 线上首页、数据获取、重新生成和离线下载均通过。
- [ ] 发布后 ERROR／WARN 日志已检查；无指标采样时已如实记录。
- [ ] 父仓库版本指针和 `ROADMAP.md` 已同步。
