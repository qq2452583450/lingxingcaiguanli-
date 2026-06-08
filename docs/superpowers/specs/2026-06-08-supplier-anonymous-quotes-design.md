# 供应商匿名报价功能设计说明

日期：2026-06-08

## 目标

在现有询比价流程不大改的前提下，增加一个供应商独立入口。材料员或管理员添加材料并发起询比价后，可以选择供应商参与报价；供应商登录自己的页面后，只能看到分配给自己的材料并提交报价。

核心要求：

- 有专门的供应商登录界面。
- 供应商可以自己注册，注册后出现在系统的供应商列表里。
- 系统管理员也可以创建供应商，并设置供应商登录账号和密码。
- 供应商登录后可以看到被选购、被邀请报价的材料，并填写报价。
- 报价对供应商之间匿名：供应商不能看到其他供应商名称、报价、是否最低价、是否被选中。
- 供应商已提交的报价，在截止前或内部锁定前允许修改。这一点很关键，避免填错价格后只能找管理员处理。

## 当前代码基础

现有相关模块：

- `blueprints/system.py`：已有供应商 CRUD 接口 `/api/suppliers`。
- `blueprints/auth.py`：内部用户登录 `/api/login`，基于 `users` 和 `roles`。
- `blueprints/inquiries.py`：询比价创建、草稿、审批、报价相关逻辑。
- `database/init_db.py`：已有 `suppliers`、`purchase_inquiry_items`、`purchase_inquiry_quotes` 等表。
- `index.html` 和 `static/js/app.js`：现有内部系统前端。

现有表里 `purchase_inquiry_quotes` 已有 `item_id`、`supplier_id`、`tax_price`、`tax_exempt_price`、`tax_rate`、`total_amount` 等字段，可以作为供应商报价的基础。

需要注意：当前正式创建询比价时，后端会过滤掉 `tax_price <= 0` 的报价行。供应商报价邀请场景需要允许先创建“待报价”的报价行，价格可以暂时为空或 0，后续由供应商填写。

## 角色和边界

### 内部用户

内部用户继续使用原有登录页和原有权限体系。

内部用户可以：

- 维护供应商基础资料。
- 为供应商创建登录账号、重置密码、启用或禁用账号。
- 在询比价单里选择参与报价的供应商。
- 发布报价邀请。
- 查看供应商提交后的完整报价对比。
- 锁定报价，进入内部评审或审批。

### 供应商用户

供应商用户使用独立登录页，不进入内部管理系统。

供应商用户可以：

- 注册供应商账号。
- 登录供应商报价页面。
- 查看自己被邀请报价的询比价单和材料明细。
- 填写、保存、提交报价。
- 在报价截止前或内部锁定前修改已提交报价。

供应商用户不能：

- 查看其他供应商。
- 查看其他供应商报价。
- 查看内部审批信息。
- 查看内部用户列表、库存、项目、系统设置等后台功能。
- 修改不属于自己的报价记录。

## 推荐流程

### 1. 供应商注册

供应商打开独立入口，填写：

- 供应商名称
- 联系人
- 手机号
- 地址
- 登录账号
- 登录密码

注册后：

- 写入 `suppliers` 表。
- 写入供应商账号表。
- 默认账号状态建议为 `pending`，显示在供应商管理里，由内部管理员确认后启用。

说明：用户原话是“注册后显示在供应商里”。为了避免外部人员随意注册后直接报价，建议默认待审核。若业务确认希望注册后立刻可登录，可以把默认状态改为 `active`。

### 2. 管理员创建供应商账号

内部系统的供应商管理新增账号区域：

- 登录账号
- 初始密码
- 账号状态：待审核 / 启用 / 禁用
- 重置密码

管理员创建供应商时，可以同时创建账号和密码。已有供应商也可以补账号。

### 3. 内部发布报价邀请

询比价单里选择材料和供应商后，内部用户点击“发布给供应商报价”。

后端应为每个“材料 + 供应商”组合创建待报价记录：

- `purchase_inquiry_quotes.supplier_id`
- `purchase_inquiry_quotes.item_id`
- 报价状态为 `pending`
- 价格字段为空或 0

发布后，供应商登录即可看到自己的待报价材料。

### 4. 供应商报价

供应商只能看到自己的报价任务。

建议页面分两层：

- 报价任务列表：询比价编号、项目、材料数量、状态、截止时间。
- 报价详情：材料名称、规格型号、单位、数量、备注、单价、税率、备注。

供应商可以先保存草稿，也可以提交报价。

提交后，只要未超过截止时间且内部未锁定报价，允许再次修改并重新提交。

### 5. 内部锁定和评审

内部用户可以锁定报价。

锁定后：

- 供应商不可再修改报价。
- 内部进入现有询比价对比、选择、审批流程。
- 现有内部报价对比可以显示供应商名称和价格。

## 数据库设计建议

### 新增 `supplier_accounts`

建议新增独立账号表，不要把供应商账号混入内部 `users` 表。

字段建议：

- `id`
- `supplier_id`
- `username`
- `password`
- `status`
- `is_active`
- `create_time`
- `last_login_time`

约束建议：

- `username` 唯一。
- `supplier_id` 关联 `suppliers.id`。
- 同一个供应商可以先按一个账号实现；字段设计保留后续多账号空间。

### 扩展 `purchase_inquiries`

建议新增：

- `quote_status`：`draft` / `collecting` / `locked`
- `quote_deadline`：报价截止时间，可为空。

### 扩展 `purchase_inquiry_quotes`

建议新增：

- `quote_status`：`pending` / `saved` / `submitted` / `locked`
- `submitted_at`
- `updated_at`
- `supplier_remark`

价格字段继续沿用现有字段，避免破坏内部报价对比逻辑。

## 后端接口建议

新增供应商门户蓝图：`blueprints/supplier_portal.py`。

供应商认证接口：

- `POST /api/supplier/register`
- `POST /api/supplier/login`
- `POST /api/supplier/logout`
- `GET /api/supplier/me`

供应商报价接口：

- `GET /api/supplier/quote-requests`
- `GET /api/supplier/quote-requests/<inquiry_id>`
- `PUT /api/supplier/quotes/<quote_id>`
- `POST /api/supplier/quotes/<quote_id>/submit`

内部接口扩展：

- `POST /api/purchase-inquiries/<id>/publish-quotes`
- `POST /api/purchase-inquiries/<id>/lock-quotes`
- 供应商管理接口支持账号创建、启用、禁用、重置密码。

## 前端设计建议

新增供应商页面：

- `supplier-portal.html`
- `static/js/supplier-portal.js`
- `static/css/supplier-portal.css`

页面区域：

- 登录
- 注册
- 报价任务列表
- 报价详情
- 保存报价
- 提交报价

内部系统改动：

- 供应商管理弹窗或表单增加账号字段。
- 询比价详情增加“发布给供应商报价”“锁定报价”操作。
- 询比价列表或详情显示报价收集状态。

## 安全规则

- 供应商登录使用单独 session，例如 `session['supplier_user']`，不要复用内部 `session['user']`。
- 密码哈希复用现有 `helpers.hash_password` 和 `helpers.verify_password`。
- 供应商接口每条 SQL 都必须按 `supplier_id` 限制数据范围。
- 供应商接口不要返回其他供应商名称、报价、最低价、选择状态。
- 供应商页面不要返回内部采购参考价、审批记录、系统用户等内部信息。
- 供应商登录增加和内部登录类似的失败次数限制。
- 供应商注册和登录继续遵守现有 CSRF 方案；如果现有登录接口有豁免，也要保持一致且明确。

## 验收标准

- 供应商可以注册，注册后内部供应商列表能看到。
- 管理员可以创建供应商账号并设置密码。
- 供应商可以登录独立页面。
- 供应商只能看到分配给自己的报价任务。
- 供应商不能通过改接口参数查看或修改其他供应商报价。
- 供应商可以保存报价。
- 供应商可以提交报价。
- 提交后，在截止前且未锁定时可以修改。
- 超过截止时间或内部锁定后不能修改。
- 内部用户可以看到供应商提交后的报价，用于现有询比价对比和审批。
- 原有内部登录、供应商管理、询比价创建、草稿、审批流程不被破坏。

