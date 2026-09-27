# 数据库、备份与恢复

## 并发连接策略

应用启动时将数据库切换到 WAL 模式，并设置 `wal_autocheckpoint=1000`。每个 HTTP 请求使用独立 SQLite 连接，连接启用外键、`synchronous=NORMAL` 和默认 15 秒忙等待。该组合适合约 100 人同时在线且读多写少的使用方式，但 SQLite 同一时刻仍只有一个写入者。

数据库、`-wal` 与 `-shm` 文件必须位于服务器本地磁盘。不要将正在运行的数据库放到 SMB、NAS、网盘同步目录或多台服务器共享目录。备份继续使用 SQLite Backup API，以获得包含 WAL 数据的一致性快照。

并发策略可通过 `TEAM_LOOP_SQLITE_BUSY_TIMEOUT_MS` 调整；修改后运行 `python scripts\concurrency_smoke_test.py`，确认 100 个混合请求无锁错误且 `PRAGMA quick_check` 返回 `ok`。

## 1. 数据文件

默认正式数据库：

```text
data/weekly_team.db
```

相关目录：

```text
data/backups/                         # 系统自动和手动备份
data/deploy/gray/weekly_team_gray.db  # 灰度数据库
data/deploy/backups/                  # 正式发布前快照
data/deploy/releases/                 # 代码发布快照
data/deploy/runtime/                  # 进程元数据和日志
```

这些内容均不应提交到 Git。

## 2. 表结构分组

### 用户与权限

| 表 | 用途 |
| --- | --- |
| `users` | 账号、姓名、角色、用户类型、密码哈希、认证来源、企业身份标识、SSO 建议组织、早例会顺序和启用状态 |
| `org_units` | 可配置组织树、路由标识、可见范围、默认用户类型与 SSO 群组映射 |
| `user_types` | 管理员自定义的用户类型、版本号、四类业务参与开关，以及保留的 `guest` 访客模板 |
| `module_permissions` | 用户类型对模块的查看、新增、修改、删除权限 |
| `members` | 与用户关联的成员画像、头像、标签、职责和排序 |
| `auth_sessions` | 持久化登录会话、设备摘要、最后活动时间、到期和撤销状态 |
| `login_attempts` | 按账号和来源地址统计失败次数及临时锁定时间 |
| `sso_login_states` | OAuth2/OIDC 登录的一次性 state 摘要、nonce、PKCE verifier、固定回调地址、安全站内回跳目标和有效期 |

`users.user_type` 必须指向一个启用的用户类型。系统账号由管理员直接分配非访客类型；SSO 自动创建的账号暂时使用 `guest`，并将 `users.classification_pending=1`。管理员单个或批量分配正式类型后，该标志自动清零。删除类型采用停用方式，且仅在没有有效用户引用时允许执行。`guest` 同时代表未登录访问与待分类 SSO 账号，服务端会强制其所有写权限和业务参与开关为关闭。

`users.employee_id` 保存工号并使用不区分大小写的唯一索引，是 SSO 与用户管理的业务关联键。企业身份使用 `users.auth_source='oidc'` 或 `'oauth2'`，并以唯一的 `external_subject=<provider>|<sub>` 保存稳定身份；工号变化时仍可通过主体识别用户，但发生工号冲突会拒绝登录。`suggested_org_unit_id` 保存最近一次 SSO 群组匹配出的建议组织，`sso_groups_json` 和 `sso_last_login_at` 用于管理员核对映射来源；登录本身不会修改现有 `org_unit_id`。管理员确认所属团队后清空建议字段。`sso_login_states.return_to` 只接受 `/` 或 `/org/...` 路径和白名单 `view` 参数，并与一次性 state 一起保存，防止开放重定向；登录成功或失败均使用该目标返回。登录事务成功或过期后会被清理；Client Secret 存在 `system_settings` 或进程环境变量中，API 永不回显明文。

`users.org_unit_id` 指向账号所属组织。`users.morning_sort_order` 保存账号在所属组织早例会中的显示顺序，索引 `idx_users_morning_order` 支持按组织稳定读取。`org_units.parent_id` 构成树，兄弟节点的 `slug` 唯一，完整路由由祖先 slug 组合生成。`visibility_mode` 为 `all/subtree/unit`；`sso_groups` 保存 JSON 数组。`team_posts.org_unit_id` 和 `meetings.org_unit_id` 记录内容创建时的组织上下文：会议和公告可向后代组织只读透传，写入仍以原组织为准。早例会、排班、签到、红黑榜和 Thank You 通过关联用户的 `org_unit_id` 只匹配当前选中组织；Thank You 记录要求发送人和接收人同时属于该组织。

组织调整不会隐式修改历史事实。需要将旧组织下的讨论或会议迁入新组织时，使用 `scripts/migrate_org_data.py`；脚本默认只预览，执行前创建 SQLite 备份，并记录逐行迁移清单供回滚。

`user_types.include_in_members/include_in_morning/include_in_rules/include_in_thanks` 控制当前名单展示与新业务数据写入，不删除历史事实。`user_types.version` 和 `morning_items.version` 用于乐观并发控制，更新语句必须同时匹配客户端读取到的版本号。早例会轻量 `version_token` 不单独持久化，而是由相关事项版本、更新时间、数量和当前人员顺序计算，避免每个轮询请求写数据库。

### 团队交流

| 表 | 用途 |
| --- | --- |
| `team_posts` | 团队讨论主题，包含分类、状态、标题、浏览量、置顶和软删除字段 |
| `team_moments` | 团队关键事件，包含组织、日期、分类、事迹和软删除字段 |
| `team_moment_images` | 团队时刻图片二进制、类型、文件名与顺序 |
| `team_post_replies` | 支持父子关系的楼中回复 |
| `team_post_reactions` | 主消息快捷回应 |
| `team_reply_reactions` | 回复快捷回应 |
| `member_posts` | 早期成员评论兼容数据 |

`team_posts.deleted_at` 与 `deleted_by` 用于主题软删除。回收站以 `team_post` 作为实体类型；恢复时只清空主题删除标记，彻底清除时由外键级联删除回复与回应。作者可以维护自己的主题，管理员承担公告、置顶和恢复治理职责。

团队时刻图片保存在 `team_moment_images.image_data`，因此数据库备份会同时包含图片，不会产生文件目录与数据库不一致的问题。`team_moments` 只在记录所属的当前团队展示，不向上级或下级透传；修改和删除同样要求当前路由直接选中该团队。回收站实体类型为 `team_moment`，彻底删除时图片由外键级联清理。

### 会议与早例会

| 表 | 用途 |
| --- | --- |
| `morning_items` | 每日事项、状态、优先级、风险、继承链和进展 |
| `meetings` | 会议日期、开始时间、主题、摘要、创建人和阶段 |
| `meeting_items` | 议题、纪要、负责人、时间盒、会前材料和顺延来源 |
| `meeting_topic_types` | 管理员按团队维护的一级议题分类和颜色，`org_unit_id` 标识归属 |
| `meeting_topic_options` | 隶属于一级分类的二级预设议题、周期和默认准备信息 |
| `meeting_topic_links` | 每场会议独立启用的议题类型 |
| `meeting_attendance` | 签到、乐捐金额和收款状态 |

### 流程中心

| 表 | 用途 |
| --- | --- |
| `process_templates` | 团队流程模板、说明、版本和停用状态 |
| `process_template_items` | 模板节点、父节点、必做标记和顺序 |
| `process_instances` | 用户从模板生成的个人流程、状态和截止日期 |
| `process_instance_items` | 个人流程的节点关系快照、勾选状态和完成人 |

`parent_item_id` 将流程组织为一棵树或由多棵树组成的森林：空值是并行起点，同一父节点的多个子节点是并行分支。生成个人流程时会复制模板项的标题、说明、必做标记、顺序和父子关系。`template_item_id` 只用于追溯来源并允许模板项删除后置空，流程执行不依赖模板当前内容。模板编辑只影响以后生成的流程；历史流程必须保持原快照。流程完成状态由必做项计算，写入节点、级联撤销下游节点和重算流程状态应在同一事务中完成。

### 业务看板

| 表 | 用途 |
| --- | --- |
| `red_black_rules` | 红黑榜细则 |
| `red_black_scores` | 个人红榜/黑榜积分事实 |
| `machines` | 按团队隔离的机台档案，`org_unit_id + name` 在团队内唯一 |
| `shifts` | 白班、夜班和工时 |
| `thank_you_votes` | Thank You 记录和事实依据 |
| `links` | 链接、标签、置顶、质量和访问量 |
| `link_categories` | 管理员维护的链接分类 |

`system_settings.red_black_show_black_points` 和 `red_black_show_black_details` 分别控制普通用户是否可见黑榜汇总及明细。它们只改变读取范围，不删除或改写历史积分事实。

### 团队规范

| 表 | 用途 |
| --- | --- |
| `norm_categories` | 按团队隔离的规范分类（目录），最多两级：`parent_id` 为空即一级目录，非空则挂在该目录下；`created_by` 记创建人，决定谁有权删；重名只在**同一上级目录内**唯一（唯一索引 `org_unit_id + COALESCE(parent_id, 0) + name`） |
| `norms` | 成员随手记的规范条目：标题、说明、适用范围、来源、状态、生效/失效日期 |
| `norm_images` | 规范正文的插图：**只存相对路径**，图片本体在 `data/uploads/norms/YYYY/MM/` 下；`norm_id` 为空表示「已上传但还没被任何条款引用」的暂存图；`deleted_at` 是软删，规范删除会进回收站、可以恢复，硬删图片会让恢复后裂图 |
| `norm_doc_versions` | 预留表：统一规范文档的发布快照结构（版本号、生效日期、修订说明、章节全文、变更摘要），**当前版本不读写** |

规范文档不是独立编辑的文本，而是 `norms` 的实时投影：**每个分类各自成一份文档**，条款号是**份内序号**（`1`、`2`、`3`…），每份文档都从 `1` 重新排，不带分类前缀；文档之间靠 `category_id` 与标题区分。没有草稿/正式版的区分，也没有发布快照。`norm_doc_versions` 仅在建表语句中保留，供将来引入版本管理时使用——这样老库无需迁移，也没有任何接口依赖它。`status` 取值为 `active`、`pending`（管理员复核标记）、`abolished`；只有 `active` 且未过 `effective_to` 的条目进入文档。分类下仍有未删除条目时不允许删除该分类（走 API 停用也同样受此限制）。

**两级目录**：一级目录下可以再建子目录（如「研发流程」下的「python研发流程」），**两级都能直接放条款**。父目录与子目录各自成一份独立文档，父目录文档**只显示直属条款**，不会把子目录的条款并进来；`parent_id` 只用于导航缩进。层级上限固定为 2：新增/移动目录时若上级本身已是二级目录，会返回 400。删除一级目录时，只要它下面还有子目录就返回 409，必须先移走或删除子目录（走 API 停用同样受限）。

**目录权限落在数据上，不落在角色上**：`norm_categories.created_by` 记录谁建的目录，删除时据此判定——`created_by` 等于当前用户即可删，管理员不看这一列、任何目录都能删。系统预置的 6 个分类由播种逻辑写入，`created_by` 为空，语义是「全团队共用的」，只有管理员能删。为什么不用角色表（`module_permissions`）表达「只能删自己建的」：那张表是**类型 × 模块**的粗粒度闸门，表达不了「同类型用户之间还要按记录归属区分」；而把归属判断放到 handler 里，`can_delete` 就能作为字段随列表一起下发给前端，前端不必把同一条规则再抄一遍。改名与删除同源，都按 `created_by` 判定归属（创建人本人或管理员）；换上级与停用仍限管理员——它们改的是「这份文档摆在哪、别人还能不能看到」，不是「我自己建的东西」。这两个操作在界面上已无入口，能力保留在 handler 与 API 层。

老库升级不需要手工迁移：`parent_id` 与 `created_by` 都由 `ensure_column` 补列（存量分类全部落到一级、`created_by` 留空即当作系统预置），启动时 `DROP INDEX IF EXISTS idx_norm_categories_unit_name` 换建成按 parent 作用域的唯一索引——旧索引范围更宽，换成范围更窄的索引不会因既有数据冲突。`data\weekly_team.db` 这类老库直接启动即可。

**插图为什么不进库**：`norm_images` 只存相对路径，字节落在 `data/uploads/norms/YYYY/MM/` 下。`scripts/db_snapshot.py` 用 `sqlite3.backup()` 整库逐页复制并跑一遍 `PRAGMA integrity_check` 全库校验，而 `deploy.ps1` 一次完整上线要生成两遍快照（灰度阶段拷正式库、Promote 阶段备份正式库）、回滚还要第三遍——图片进库会让这些操作的开销随图片量线性增长，`data/backups/` 里也会堆起同等体积的完整副本。`data/` 同时是唯一被部署流程排除的目录（手工覆盖用 `robocopy /MIR /XD data`；release 快照只拷 `server.py`、`team_loop`、`static`、`previews`），上传文件放这里既不会被发布快照固化，也不会被镜像同步删掉。这张表不需要迁移：`CREATE TABLE IF NOT EXISTS` 与 `idx_norm_images_norm`、`idx_norm_images_orphan` 两个索引在启动时自动补齐，存量数据一条不动。

### 系统治理

| 表 | 用途 |
| --- | --- |
| `system_settings` | 系统名称和业务参数 |
| `audit_logs` | 关键写操作审计 |
| `backups` | 备份文件及校验、恢复状态 |
| `recycle_bin` | 软删除记录索引 |
| `reminder_reads` | 用户提醒已读状态 |
| `schema_migrations` | 迁移兼容记录 |

## 3. 迁移机制

启动时 `init_db()` 会：

1. 创建不存在的表；
2. 通过 `ensure_column()` 增加缺少字段；
3. 执行幂等的数据兼容更新；
4. 写入默认配置、用户类型和示例基础数据（仅在对应数据为空时）。

旧库首次升级时会执行两项带迁移标记的受控表重建：为议题类型和机台补充 `org_unit_id`。旧议题库先归属根团队，再复制一份独立模板到尚无议题库的有效团队；旧机台根据既有排班人员所属团队拆分并重绑排班。迁移完成后分别使用团队内唯一约束，后续新增和查询均按当前团队过滤。正式升级前必须先备份，并在灰度库运行 `PRAGMA foreign_key_check`、组织范围测试和排班抽查。

验证迁移：

```powershell
python server.py --migrate-only
```

迁移代码必须允许重复执行。不要把 SQLite 数据库文件作为迁移载体提交到仓库。

## 4. 自动备份

系统启动和日常请求期间会检查当天是否已自动备份。相关设置：

- `backup_auto_enabled`：是否启用；
- `backup_retention_days`：自动备份保留天数，0 表示不自动清理。

备份使用 SQLite Backup API，而不是直接复制正在写入的数据库文件，因此可以获得一致性快照。

## 5. 备份校验

系统管理中的“校验”会在独立连接中运行 `PRAGMA quick_check`，并检查关键业务表是否存在。校验通过只表示文件结构可读取，不替代业务层恢复演练。

建议每月：

1. 创建最新手动备份；
2. 校验备份；
3. 在灰度或隔离目录恢复；
4. 登录并抽查用户、会议、早例会、排班和链接；
5. 记录演练时间和结果。

## 6. 一键恢复

管理员选择备份并确认恢复后，系统会：

1. 先校验目标备份；
2. 创建当前数据库的恢复前备份；
3. 使用 SQLite Backup API 覆盖当前数据库；
4. 重新执行 `init_db()`；
5. 记录恢复人、时间、结果和审计日志。

恢复会覆盖当前数据。执行前应停止或通知其他用户，恢复后所有人重新刷新页面并检查关键数据。

## 7. 手工快照

```powershell
python scripts\db_snapshot.py `
  --source data\weekly_team.db `
  --target D:\TeamLoopBackup\weekly_team_20260712.db
```

目标目录应与服务器磁盘分离。不要使用资源管理器直接复制正在频繁写入的 SQLite 文件作为唯一备份方式。

## 8. 数据安全

- 密码以加盐哈希保存，会话令牌仅保存摘要；数据库仍包含员工和业务信息；
- 限制 `data/` 目录的 Windows 文件权限；
- 不把数据库放在公开共享目录；
- 不在截图、Issue 或日志中暴露账号、事实依据和审计详情；
- 对外提供服务前必须增加 HTTPS、访问控制和安全加固。

## 9. 灰度规模化数据

`scripts/seed_scale_mock.py` 用于在灰度数据库中构造 100 人规模的数据分布。它不是启动迁移，也不会由正式服务自动执行。

脚本使用以下边界避免污染真实数据：

- 仅允许数据库路径位于 `gray` 目录或文件名以 `_gray.db` 结尾；
- 通过 SQLite Backup API 在写入前创建快照；
- 真实账号不删除、不改密码，只补充 `mock###` 账号；
- 重建业务数据时只处理 `[MOCK]`、`MOCK-` 及 Mock 账号关联的数据；
- 所有模块写入在单个事务中完成，任何异常都会整体回滚；
- 结束时执行外键检查和 `quick_check`。

灰度发布会重建灰度数据库，因此正确顺序是“部署灰度 -> 生成 Mock -> 体验与压测”。不要把 Mock 灰度库作为生产备份或组织迁移数据源。
