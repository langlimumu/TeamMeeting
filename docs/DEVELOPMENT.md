# Team Loop 二次开发指南

## 1. 技术栈与设计目标

Team Loop 是无构建步骤的模块化单体应用：

- 后端：Python 标准库 `http.server`、`sqlite3`；
- 前端：原生 ES Module、HTML、CSS；
- 数据库：SQLite；
- 部署：Windows PowerShell 与批处理脚本；
- 第三方前端资源：放在 `static/vendor/`，运行时不依赖外网。

这种结构适合小团队低成本部署。二次开发应优先保持“无需 pip/npm 安装”和“单目录可发布”的特性。

## 2. 项目结构

```text
TeamMeeting/
├─ server.py                    # 兼容启动入口，仅组装并启动后端
├─ team_loop/
│  ├─ config.py                 # 路径、系统常量、权限初始值、并发参数
│  ├─ common.py                 # 日期、JSON、密码、SQLite 连接等通用能力
│  ├─ database.py               # 表结构、幂等迁移、种子数据、备份基础能力
│  ├─ sso_http.py               # OAuth2/OIDC HTTPS 连接池与 Discovery 缓存
│  ├─ permissions.py            # 模块操作权限与日期过滤
│  ├─ http_server.py            # 有界线程 HTTP Server
│  ├─ handler.py                # 组合各业务 Handler Mixin
│  └─ handlers/
│     ├─ request.py             # HTTP 协议、静态资源、路由与组织访问基础
│     ├─ accounts.py            # 登录、SSO、用户类型、组织、用户和成员
│     ├─ collaboration.py       # 团队时刻、讨论区、早例会和流程中心
│     ├─ operations.py          # 红黑榜、会议、链接、排班和 Thank You
│     └─ system.py              # 回收站、归档、备份、配置和审计
├─ static/
│  ├─ index.html                # 页面骨架、表单、弹窗
│  ├─ app.js                    # 前端状态、渲染、接口调用、交互绑定
│  ├─ style.css                 # 基础样式、主题和响应式规则
│  └─ vendor/                   # 本地化第三方静态资源
├─ scripts/
│  ├─ dev_server.py             # 文件监视与开发热更新
│  ├─ smoke_test.py             # 部署后的只读冒烟测试
│  ├─ process_flow_smoke_test.py # 流程模板、快照、权限与进度测试
│  ├─ sso_smoke_test.py         # OAuth2/OIDC 工号关联集成测试
│  ├─ forum_smoke_test.py       # 讨论区权限、回复、表情和回收测试
│  ├─ proxy_smoke_test.py       # 可信代理、真实 IP 和 Secure Cookie 测试
│  ├─ nginx_proxy.ps1           # Nginx 配置生成与生命周期管理
│  └─ db_snapshot.py            # SQLite 一致性快照
├─ deploy.ps1                   # 灰度、正式、回滚和状态管理
├─ start_*.bat / deploy_*.bat   # Windows 双击入口
├─ docs/                        # 用户、开发和运维文档
├─ skills/                      # 可分发的 Codex 项目 Skill
└─ data/                        # 数据库、备份、日志和发布快照，不进入 Git
```

## 3. 请求生命周期

1. 浏览器通过 `static/app.js` 的 `api()` 发起请求。
2. `team_loop.handlers.request.RequestHandlerMixin` 解析路径、方法和 JSON。
3. `module_for_path()` 将业务接口映射到模块权限。
4. 公开接口直接执行；受保护接口先读取会话并校验模块及操作权限。
5. 业务方法通过 `connect()` 访问 SQLite。
6. 写操作调用 `write_audit()` 记录审计日志。
7. 前端更新 `state` 并调用对应 `render*()` 函数重绘模块；页面重新获得焦点、重新显示或切换模块时会同步认证与最新数据。

接口统一返回 JSON。业务异常使用 `AppError(status, message)`，前端通过 Toast 展示 `error` 字段。

## 4. 前端组织方式

### 页面注册

新增一级模块时需要同步处理：

1. 在 `static/index.html` 增加 `<section id="module-key" class="page">`；
2. 在 `static/app.js` 的 `pages` 增加导航配置；
3. 为模块增加 `loadXxx()` 和 `renderXxx()`；
4. 在 `refreshPageData()` 的 loader 映射中注册；
5. 在 `team_loop/config.py` 的 `MODULE_CATALOG`、初始类型权限，以及 `team_loop/handlers/request.py` 的 `module_for_path()` 中注册；
6. 访客范围由数据库中的 `guest` 权限模板控制，不要另加前端硬编码白名单。

团队时刻是新增模块的完整参考：`team_moments` 与 `team_moment_images` 使用独立表，读取、写入和图片访问都通过当前选中组织精确过滤，不允许祖先记录向下透传。图片接口在 JSON 路由前单独输出二进制，但仍必须执行会话、模块和组织权限校验。修改该模块后运行 `python scripts/team_moments_smoke_test.py` 和组织范围测试。

### 状态与刷新

全局数据存放在 `state`。切换页面时会重新调用模块 loader，以获取最新数据。写操作完成后优先只刷新受影响模块；跨模块数据同步时使用 `refreshAll()`。

公共时间筛选由 `setDefaultDates()` 初始化为当月首日至今天，不要在单独页面重复覆盖。排班日期范围分别使用 `selectedShiftDate` 和 `selectedShiftEndDate`；月历重绘不得把用户选择的结束日期强制重置为开始日期。

所有来自用户或接口的文本在插入 HTML 字符串前必须经过 `escapeHtml()`。日期统一使用 `YYYY-MM-DD`，显示时使用 `shortDate()` 或 `shortDateTime()`。

### 表单和弹窗

- 简单创建可以使用页面内表单；
- 修改、详情、长内容和确认删除使用弹窗；
- 绑定新表单时复用 `bindForm()` 或在统一的 `submit` 事件中处理；
- 动态生成的按钮使用事件委托，不要为每一行重复注册监听器；
- 所有按钮必须有明确的禁用、加载、成功或失败反馈。

### CSS

基础设计变量位于 `style.css` 顶部。新增样式应：

- 默认适配 Miro 主题，并检查其他主题的覆盖规则；
- 使用稳定的 grid/flex 约束，不依赖视口宽度缩放字体；
- 在 980px、720px 等已有断点检查布局；
- 长文本使用 `overflow-wrap: anywhere`；
- 表格或日历在窄屏提供滚动，不允许内容遮挡。

响应式修改还必须覆盖 `1440`、`1024`、`768` 和 `390` 像素宽度。页面本身不得出现横向滚动，宽表格、日历、脑图和流程树只能在自己的容器内滚动。`900px` 以下应保持当前导航可见并折叠次要账户操作；移动端弹窗使用 `100dvh`、适配安全区，表单控件字号不得低于 `16px`，避免 iOS 聚焦时自动放大。浮层需要分别验证视口左右边缘。

## 5. 后端开发约定

### 路由

路由集中在 `team_loop/handlers/request.py` 的 API 分发区域，业务实现放进对应领域 Mixin。推荐形式：

```python
if path == "/api/example":
    if method == "GET":
        return {"items": self.list_examples()}
    if method == "POST":
        return self.create_example()
```

动态资源使用 `parts` 判断，并在转换 ID 前确认路径长度。对外错误使用清晰中文，不返回 SQL、文件路径或堆栈。

### 权限

权限不是仅隐藏按钮。每个写接口都必须在服务端调用以下一种校验：

- `self.require_admin()`：仅管理员；
- 当前用户与资源所有者判断：只能修改自己的内容；
- 模块操作权限：由统一路由权限层处理。

新增模块时应同时定义 `view/create/edit/delete` 的初始权限。用户类型可由管理员动态创建、改名和删除，业务代码不得依赖类型名称或固定类型 key。`guest` 是保留的只读模板，不能分配给账号，也不能获得写权限。管理员切换用户视图只影响前端展示，服务端仍识别管理员账号，因此危险操作必须有显式确认。

模块权限和业务参与资格不是同一概念。团队成员、早例会、红黑榜和 Thank You 使用 `user_types` 上独立的 `include_in_*` 字段；查询当前名单和创建新事实时均需在服务端校验。调整参与资格不得删除历史事项、积分或感谢记录。

用户类型与早例会事项采用乐观并发控制。前端更新时传 `expected_version`；服务端使用 `WHERE version=?` 原子更新，冲突返回 409 并要求客户端刷新。批量排班也必须先完成整批冲突校验再写入，避免部分成功。

登录会话持久化在 SQLite 中，只保存令牌摘要。新增认证功能时同时考虑超时、撤销、密码修改后的其他设备退出、失败次数锁定和 401 后前端自动回到登录视图。

企业 SSO 使用 OAuth2/OIDC Authorization Code + PKCE，可走 Issuer Discovery 或手动三端点。手动配置页按 OAuth2 认证地址、Access Token 地址、UserInfo 地址和应用凭据分组，但存储键继续使用 `sso_authorization_url/sso_token_url/sso_userinfo_url`，避免仅因文案调整破坏环境变量和既有数据库。授权、Token 和 UserInfo 地址必须为 HTTPS，本机集成测试仅允许 `localhost/127.0.0.1` 使用 HTTP。`team_loop/sso_http.py` 按身份平台 Origin 维护有界 HTTP/1.1 Keep-Alive 连接池，Discovery 使用短缓存和单飞锁避免登录高峰重复握手；跨域重定向与 Token POST 重定向必须拒绝，不能把 Bearer Token 或 Client Secret 转发到未配置域名。state 只能使用一次，Client Secret 不得出现在公开设置、日志、Git 或前端源码中；密码型设置留空表示保留旧值。前端发起 SSO 时把当前 `/org/...` 路径和 `view` 模块放入 `return_to`，后端必须经过 `sanitize_sso_return_to()` 后绑定到 `sso_login_states`，回调不得直接信任浏览器或身份平台传回的跳转地址。登录成功和失败都通过已保存目标返回；用户无权访问原组织或模块时由现有组织与模块权限逻辑自动降级。`users.employee_id` 是 SSO 工号关联主键，首次登录先按工号关联已有用户；不存在时自动创建 `user_type=guest, classification_pending=1` 的只读账号，由管理员后续分类。`external_subject` 保存身份平台稳定主体。SSO 群组不得直接覆盖 `org_unit_id`，只更新 `suggested_org_unit_id/sso_groups_json/sso_last_login_at`；管理员确认团队后再清空建议。修改认证链路后运行 `python scripts\sso_smoke_test.py` 和 `python scripts\sso_pool_smoke_test.py`，验证业务映射、安全边界、连接复用和 Discovery 缓存。

组织层级由 `org_units` 构成树，业务接口通过 `organization_context()` 计算当前账号允许访问、当前路由实际可见、祖先透传和同根协作组织 ID。前端传入的 `X-Team-Org-Path` 只是选择意图，不能作为授权依据。人员型业务要区分“账号允许切换的组织”和“当前层级直接成员”：早例会、排班、签到、红黑榜与 Thank You 统一使用 `organization_current_user_filter()`；成员页等确需子树视图的功能才使用 `organization_user_filter()`。管理员虽可切换全部组织，业务页面仍应按所选层级过滤。

成员拖动排序提交的必须是当前组织路由完整可见成员集合。`update_member_order()` 应复用 `organization_user_filter()` 校验，而不是拿全库有效成员作比较；响应也必须带当前组织上下文重新查询，保证拖动后前端不会突然混入其他团队。桌面拖动之外保留上移/下移操作，作为触屏与键盘回退。

组织数据必须先声明归属和传播方式，不能用一个“可见组织集合”同时决定读写：

- `selected.id`：当前选中组织；早例会、排班、签到、红黑榜和 Thank You 通过 `organization_current_user_filter()` 只匹配该组织的直接成员；
- `visible_ids`：当前账号在所选路由下可查看的组织集合，只用于明确需要子树聚合的页面；
- `ancestor_ids/inherited_ids`：只用于明确允许向下透传的上级记录；当前仅会议和 `announcement` 团队公告；
- `collaboration_ids`：保留给明确声明的跨团队协作功能，不得默认用于人员名单；
- 上级会议和公告在下级只读，原记录的编辑、删除、置顶、签到和议题修改仍必须通过直接组织访问校验；公告回复和表情可在下级参与；
- 议题库、机台档案和团队时刻是团队自有资产，统一使用 `organization_current_entity_filter()`，不向祖先、后代或兄弟团队透传；
- 上层会议的议题责任人和管理员工作台检查属于协调操作，可使用 `organization_user_filter()` 覆盖当前可访问子树；签到、排班、积分、感谢和早例会名单不得因此扩大；
- Thank You 候选人、动态和排名都要求发送人与接收人属于当前选中组织，跨团队记录不在任一层级自动汇总。

早例会多人协作采用轻量版本轮询，不轮询完整事项列表。`GET /api/morning-items/version` 由当天及上个工作日相关事项版本和当前人员顺序生成令牌；前端仅在令牌变化且没有活跃输入时刷新完整数据。编辑中只标记待刷新，防止定时更新覆盖未提交内容。管理员排序通过 `PATCH /api/morning-items/order` 提交当前层级完整早例会人员集合，服务端必须验证无遗漏、无越层账号。

SSO 使用配置项 `sso_group_claim` 读取群组，`match_sso_org_unit()` 只返回明确匹配且最深的组织。匹配结果只能作为管理员建议，不允许在登录回调里迁移已有账号或历史记录；自动创建的新账号回落到根组织。登录完成后优先返回发起认证时保存的站内组织路径和模块；若账号无权访问，`organization_context()` 与 `switchPage()` 分别回落到账号正式组织和第一个可用模块。历史 `team_posts/meetings` 迁移必须使用 `scripts/migrate_org_data.py` 先预览、自动备份并输出回滚清单。修改组织范围或 SSO 群组映射后运行 `python scripts\organization_scope_smoke_test.py`、`python scripts\sso_smoke_test.py` 和 `python scripts\org_data_migration_test.py`。

公共域名必须通过本机 Nginx 代理。`TEAM_LOOP_TRUST_PROXY=1` 只允许回环地址代理提供 `X-Forwarded-For` 和 `X-Forwarded-Proto`，`TEAM_LOOP_REQUIRE_HTTPS=1` 拒绝没有可信 HTTPS 标记的登录及所有写请求。不要把开启可信代理的后端监听到公网。HTTPS 代理请求必须签发 `Secure` 会话 Cookie，并用转发后的真实 IP执行登录限流、会话记录和审计。修改该链路后运行 `python scripts\proxy_smoke_test.py`，确认直连 HTTP 登录返回 426。

团队讨论区的完整 Emoji 选择器和中文数据都放在 `static/vendor/emoji-picker-element/` 与 `static/vendor/emoji-picker-element-data/`。部署环境不得依赖 CDN；修改选择器后应在断网或仅局域网条件下验证表情分类、搜索、发送和再次点击撤销。

讨论主题采用软删除。主题作者可编辑、删除自己的内容，管理员可置顶、发布公告、标记已解决及从回收站恢复。公告分类和置顶能力必须在服务端校验；列表、详情、回复写入都必须排除已删除主题。修改论坛链路后运行 `python scripts\forum_smoke_test.py`，验证越权拦截、嵌套回复、任意 Emoji、删除隐藏与恢复后回复保留。

会议创建遵循 `meetings.create` 操作权限，不应写死为管理员；一级议题分类和二级预设议题按当前团队隔离，维护仍是管理员能力。创建会议后通过 `/api/meetings/{id}/agenda-options` 批量加入当前会议所属团队的预设议题并指定当前子树责任人。`link_meeting_topic()` 也必须校验会议与议题类型的 `org_unit_id` 相同，不能只依赖前端选项。`meetings.start_time` 使用 `HH:MM`，为空表示未指定开始时间。

流程中心的模板属于组织，当前团队可以读取祖先模板。所有已登录且拥有流程查看权限的成员都能在当前团队创建模板；非管理员只管理自己创建的模板，管理员管理当前团队全部模板，祖先模板始终只读。模板节点只允许引用排在自己之前的父节点；空父节点表示并行起点，同父节点的多个子节点表示树形分支。脑图编辑器不保存布局坐标，只是有序节点与 `parent_key` 的即时投影；选中节点后只显示该节点属性，添加子步骤继承选中节点，添加并行线创建空父节点。必做节点不能依赖可选节点。用户从模板生成流程时必须复制节点及父子关系快照，不能在查询时动态引用模板项，否则模板调整会改写历史执行事实。子节点完成前必须验证父节点已完成；取消父节点时应在同一事务递归撤销下游节点、重算流程状态并写审计日志。修改该模块后运行 `python scripts\process_flow_smoke_test.py`。

红黑榜黑榜可见性必须在服务端和前端同时执行。普通用户调用 `/api/scores` 或 `/api/dashboards/red-black` 时，服务端根据两个 `red_black_show_black_*` 配置裁剪结果；前端隐藏只用于管理员切换用户视图时保持一致体验，不能替代接口过滤。

### 数据写入

- 使用 SQL 参数绑定，禁止拼接用户输入；
- 多步写操作放在同一个 `with connect() as conn` 事务中；
- 删除历史业务数据优先软删除并进入回收站；
- 写操作应调用 `write_audit()`；
- 不在 API 中返回密码哈希、会话标识或完整敏感信息。

## 6. 数据库迁移

`team_loop/database.py` 的 `init_db()` 每次启动都会执行，迁移必须幂等。

新增表使用 `CREATE TABLE IF NOT EXISTS`。为现有表增加字段使用：

```python
ensure_column(conn, "table_name", "column_name", "TEXT")
```

禁止在启动迁移中直接删除列、重建正式表或覆盖业务数据。需要数据转换时使用带条件的 `UPDATE`，确保重复执行不会改变已迁移数据。

修改数据库后至少验证：

```powershell
python server.py --migrate-only
python -m compileall -q server.py team_loop scripts
python scripts\organization_scope_smoke_test.py
```

数据库详细说明见 [DATABASE.md](DATABASE.md)。

## 7. 本地开发

推荐运行：

```powershell
python scripts\dev_server.py --host 127.0.0.1 --port 8000
```

它会监视 `server.py`、`team_loop/`、`static/` 和 `previews/` 中的 Python、HTML、CSS、JavaScript 与 JSON 文件。保存后后端自动重启，开发页面会轮询健康接口并刷新。

不要让开发服务连接正式数据库进行破坏性测试。复杂数据迁移和写操作应在灰度数据库上验证。

## 8. 验证清单

每次提交前运行：

```powershell
python -m compileall -q server.py team_loop scripts
node --check static\app.js
git diff --check
python scripts\process_flow_smoke_test.py
python scripts\sso_smoke_test.py
python scripts\sso_pool_smoke_test.py
python scripts\morning_retention_smoke_test.py
python scripts\forum_smoke_test.py
python scripts\team_moments_smoke_test.py
python scripts\proxy_smoke_test.py
python scripts\concurrency_smoke_test.py
```

功能验证至少覆盖：

- 管理员视图与用户视图；
- 至少两种自定义用户类型及不同操作权限；
- 批量调整账号类型，以及四类业务参与名单互相独立；
- 访客动态只读范围；
- 删除仍有用户的类型时必须被服务端阻止；
- 页面刷新与页面切换后的数据一致性；
- 桌面宽屏、窄屏和手机宽度；
- 写操作成功、失败、重复点击及空数据状态；
- 灰度迁移、健康检查和冒烟测试；
- 100 个并发混合请求无数据库锁错误，WAL 模式和数据库完整性检查正常。

安全与并发改动还应在灰度执行：

```powershell
python scripts\safety_feature_test.py --base-url http://127.0.0.1:8001 --database data\deploy\gray\weekly_team_gray.db
```

## 9. 并发与容量边界

当前运行时面向约 100 人同时在线、读取明显多于写入的团队协作场景：

- `BoundedThreadingHTTPServer` 默认最多处理 64 个活动请求，其余请求在监听队列等待，避免瞬时请求无限创建线程；
- SQLite 使用 WAL，让读取与单个写入可以并行；写入仍按 SQLite 规则串行；
- 每个请求使用独立连接，启用外键、15 秒 `busy_timeout` 和 `synchronous=NORMAL`；
- 会话最后访问时间最多每分钟更新一次，避免每个读取请求都产生写入；
- 图片、静态资源和备份采用流式或分块传输，业务数据库不能放在网络共享盘。

可通过环境变量调整：

```text
TEAM_LOOP_HTTP_MAX_WORKERS=64
TEAM_LOOP_HTTP_REQUEST_QUEUE_SIZE=256
TEAM_LOOP_SQLITE_BUSY_TIMEOUT_MS=15000
```

不应只为追求数字盲目增大线程数。调整后必须运行 `python scripts\concurrency_smoke_test.py`。如果实际出现持续批量写入、P95 明显超过 2 秒或频繁触发 busy timeout，应保持 HTTP/API 层不变，将数据库访问层迁移到 PostgreSQL，而不是继续放大 SQLite 锁等待。

## 10. 发布边界

开发完成后先执行灰度发布，在 8001 端口使用正式库快照验证。确认后再执行 `Promote`。不要把灰度数据库复制回正式数据库，也不要直接替换正在使用的 SQLite 文件。

完整流程见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 11. 100 人规模 Mock 数据

需要检查大列表、跨组织数据、滚动区域和 100 人并发场景时，先完成灰度部署，再执行：

```powershell
python scripts\seed_scale_mock.py --dry-run
python scripts\seed_scale_mock.py
```

脚本默认只写入 `data/deploy/gray/weekly_team_gray.db`，并拒绝不在 `gray` 目录且文件名不是 `*_gray.db` 的数据库。写入前会使用 SQLite Backup API 在灰度目录的 `mock_backups/` 下生成一致性备份。

默认行为如下：

- 保留现有真实账号和业务数据，补足到 100 个活跃账号；
- Mock 账号使用 `mock001` 起的固定命名，并服从现有用户类型、组织和业务参与开关；
- 生成跨日期、跨团队的成员、早例会、会议签到、排班、红黑榜、Thank You、论坛、链接、流程和团队时刻数据；
- Mock 业务标题或依据使用 `[MOCK]` 标识，机台使用 `MOCK-` 前缀；
- 使用固定随机种子，可重复执行；再次执行会清理上一批 Mock 业务数据后重建，不会持续累加；
- 写入后自动执行活跃人数、Thank You 每周上限、自我感谢、外键和 `PRAGMA quick_check` 校验。

可调整目标人数和随机种子：

```powershell
python scripts\seed_scale_mock.py --target-users 100 --seed 20260811
```

Mock 账号仅用于灰度体验，禁止把灰度数据库、`mock_backups/` 或统一测试密码提交到 Git，也禁止将生成后的灰度库提升或复制为正式数据库。重新执行 `deploy.ps1 -Action Gray` 会从正式库重新制作灰度快照，因此会清除此前生成的 Mock 数据；需要体验时应在灰度部署完成后最后执行本脚本。
