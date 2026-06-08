# Claude Code 开发计划：供应商匿名报价

日期：2026-06-08

## 给 Claude Code 的开工提示

请先读取：

- `CLAUDE.md`
- `docs/superpowers/specs/2026-06-08-supplier-anonymous-quotes-design.md`
- 本计划文件

开发要求：

- 在 `dev` 分支开发。
- 不要提交、推送、合并、部署，除非用户在当前对话明确同意。
- 不要改动无关文件。
- 遇到已有未提交文件，先 `git status --short`，只处理本功能相关文件。
- 保持现有 Flask + SQLite + 原生 HTML/CSS/JS 架构。
- 优先小步改动，每完成一层跑一次相关测试。

## 目标

新增供应商独立登录和匿名报价功能。供应商可以注册或由管理员创建账号；供应商登录后只能看到自己被邀请报价的材料，并提交报价。已提交报价在截止前或内部锁定前允许修改。

## 当前重点文件

后端：

- `app.py`
- `blueprints/auth.py`
- `blueprints/system.py`
- `blueprints/inquiries.py`
- `database/init_db.py`
- 可能存在的自动补字段脚本，例如 `database/auto_fix.py`
- `helpers.py`

前端：

- `index.html`
- `static/js/app.js`
- `static/css/`

测试：

- `tests/`

## 任务 1：基线检查

1. 确认分支：

```powershell
git branch --show-current
git status --short
```

2. 查看现有测试命令，优先运行项目已有测试：

```powershell
pytest
```

如果全量测试太慢或现有环境缺依赖，记录失败原因，再跑和本功能相关的后端测试。

## 任务 2：数据库结构

修改 `database/init_db.py`，并同步现有数据库自动补字段逻辑。

新增表 `supplier_accounts`：

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `supplier_id INTEGER NOT NULL`
- `username TEXT NOT NULL UNIQUE`
- `password TEXT NOT NULL`
- `status TEXT DEFAULT 'pending'`
- `is_active INTEGER DEFAULT 0`
- `create_time TEXT`
- `last_login_time TEXT`

扩展 `purchase_inquiries`：

- `quote_status TEXT DEFAULT 'draft'`
- `quote_deadline TEXT`

扩展 `purchase_inquiry_quotes`：

- `quote_status TEXT DEFAULT 'pending'`
- `submitted_at TEXT`
- `updated_at TEXT`
- `supplier_remark TEXT`

实现要求：

- 新库初始化能创建这些字段。
- 老库启动时能自动补字段。
- 字段补丁要幂等，重复运行不能报错。

建议新增或更新测试：

- 初始化数据库后存在 `supplier_accounts` 表。
- 老表补字段逻辑重复运行不报错。

## 任务 3：供应商账号和认证

新增 `blueprints/supplier_portal.py`，并在 `app.py` 注册蓝图。

实现接口：

- `POST /api/supplier/register`
- `POST /api/supplier/login`
- `POST /api/supplier/logout`
- `GET /api/supplier/me`

实现规则：

- 使用 `session['supplier_user']` 保存供应商登录态。
- 不要复用内部 `session['user']`。
- 密码哈希复用现有 `helpers.hash_password` 和 `helpers.verify_password`。
- 登录时只允许 `status='active'` 且 `is_active=1` 的账号进入。
- 注册时创建 `suppliers` 记录和 `supplier_accounts` 记录。
- 注册后的账号默认建议为 `pending` 和 `is_active=0`。
- 返回错误信息要简洁，不暴露账号是否存在的过多细节。

测试重点：

- 注册后供应商表能看到新供应商。
- 待审核账号不能登录。
- 启用账号可以登录。
- 供应商登录不会变成内部用户登录态。

## 任务 4：内部供应商管理增加账号能力

修改 `blueprints/system.py` 的供应商接口。

目标：

- 获取供应商列表时返回账号状态信息，但不要返回密码哈希。
- 创建供应商时可选创建账号和初始密码。
- 更新供应商时可启用、禁用账号。
- 支持重置供应商账号密码。

建议接口方式：

- 保持现有 `/api/suppliers` GET/POST/PUT/DELETE 尽量兼容。
- 新增 `POST /api/suppliers/<supplier_id>/account/reset-password`。
- 新增或扩展 `PUT /api/suppliers/<supplier_id>/account`。

前端修改：

- 在内部供应商管理弹窗中增加账号、初始密码、账号状态。
- 供应商列表展示账号状态。
- 管理员可以启用、禁用、重置密码。

注意：

- 不要要求材料员一定能管理供应商账号。账号管理建议仅系统管理员可用。
- 删除供应商前要考虑是否已有报价记录；现有逻辑若已有保护，继续保留。

## 任务 5：报价邀请和报价状态

修改 `blueprints/inquiries.py`。

新增内部接口：

- `POST /api/purchase-inquiries/<id>/publish-quotes`
- `POST /api/purchase-inquiries/<id>/lock-quotes`

发布报价逻辑：

- 根据询比价单材料和选中的供应商，创建 `purchase_inquiry_quotes` 待报价记录。
- 允许价格为空或 0，状态为 `pending`。
- 如果同一 `item_id + supplier_id` 已存在，不重复创建。
- 把询比价单 `quote_status` 设置为 `collecting`。

锁定逻辑：

- 把询比价单 `quote_status` 设置为 `locked`。
- 把相关报价行设置为 `locked` 或禁止继续修改。

保持兼容：

- 不破坏现有内部直接录入报价的流程。
- 不破坏草稿保存。
- 不破坏审批流程。

测试重点：

- 发布后生成待报价记录。
- 重复发布不重复生成。
- 锁定后供应商不能改价。

## 任务 6：供应商报价接口

继续在 `blueprints/supplier_portal.py` 实现：

- `GET /api/supplier/quote-requests`
- `GET /api/supplier/quote-requests/<inquiry_id>`
- `PUT /api/supplier/quotes/<quote_id>`
- `POST /api/supplier/quotes/<quote_id>/submit`

查询规则：

- 必须通过 `supplier_id` 过滤。
- 列表只返回属于当前供应商的询比价任务。
- 详情只返回属于当前供应商的材料和报价行。
- 不返回其他供应商报价。
- 不返回内部审批记录。
- 不返回最低价、是否选中等内部对比字段。

保存报价：

- 可更新 `tax_price`、`tax_rate`、`supplier_remark`。
- 后端重新计算不含税价和总价，避免前端传错。
- 状态可为 `saved`。

提交报价：

- 校验价格合法。
- 写入 `submitted_at`。
- 状态改为 `submitted`。

允许修改条件：

- 当前询比价 `quote_status != 'locked'`。
- 如果有 `quote_deadline`，当前时间不能晚于截止时间。

测试重点：

- 供应商 A 不能看供应商 B 的报价。
- 供应商 A 不能修改供应商 B 的报价。
- 已提交报价在未锁定前可以修改。
- 锁定后不能修改。
- 过截止时间不能修改。

## 任务 7：供应商门户页面

新增：

- `supplier-portal.html`
- `static/js/supplier-portal.js`
- `static/css/supplier-portal.css`

页面要求：

- 独立供应商登录页。
- 注册入口。
- 登录后显示报价任务列表。
- 点击任务进入材料报价详情。
- 支持保存和提交。
- 已锁定或过期时输入框禁用。
- 页面不要出现内部管理菜单。

设计要求：

- 保持业务系统风格，清晰、紧凑、可扫描。
- 不做营销式落地页。
- 移动端至少可正常填写报价。

## 任务 8：内部页面联动

修改 `index.html` 和 `static/js/app.js`。

增加：

- 供应商管理账号字段。
- 询比价详情或操作区显示报价状态。
- 发布报价邀请按钮。
- 锁定报价按钮。
- 报价截止时间输入。

注意：

- 操作按钮按权限显示。
- 草稿、审批、已完成等原有状态不要被新状态覆盖混乱。
- `quote_status` 是报价收集状态，不一定等于单据审批状态。

## 任务 9：测试和手工验收

优先补后端测试。

建议新增测试文件：

- `tests/test_supplier_portal_auth.py`
- `tests/test_supplier_portal_quotes.py`
- 或合并进现有相关测试文件。

必须覆盖：

- 注册供应商。
- 管理员启用账号。
- 供应商登录。
- 发布报价邀请。
- 供应商只能看到自己的报价。
- 供应商保存和提交报价。
- 提交后允许在未锁定前修改。
- 锁定后拒绝修改。
- 内部报价对比还能看到提交价格。

运行：

```powershell
pytest
```

如果全量测试有历史失败，至少运行新增测试和相关询比价测试，并记录失败原因。

## 任务 10：完成前检查

完成后执行：

```powershell
git status --short
pytest
```

汇报时说明：

- 改了哪些文件。
- 哪些功能已实现。
- 跑了哪些测试，结果如何。
- 是否存在未解决问题。
- 不要提交、推送、部署，除非用户明确同意。

## 风险点

- 现有询比价创建逻辑会过滤 0 价格报价，发布供应商报价时不能复用这段过滤逻辑。
- 供应商账号不要和内部用户混用，否则权限风险很大。
- 供应商接口每个查询都必须带 `supplier_id` 限制。
- 提交后允许修改的规则要和锁定、截止时间一起判断。
- 不要把内部参考价、审批信息、其他供应商报价泄露给供应商门户。

