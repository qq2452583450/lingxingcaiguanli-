# 零星材管理系统 - Web版

## 快速启动

### 方法一：一键启动（推荐）
1. 双击 `启动Web.bat` 文件
2. 系统会自动：
   - 检查并安装依赖
   - 初始化数据库（首次）
   - 启动 Web 服务
   - 自动打开浏览器

### 方法二：命令行启动
```bash
# 设置环境变量
$env:SECRET_KEY="your-secret-key-here"

# 安装依赖
pip install -r requirements.txt

# 启动应用
python app.py
```

## 访问地址
- 本地访问：http://localhost:5000
- 局域网访问：http://<你的IP地址>:5000

## 系统要求
- Python 3.8 或更高版本
- 支持 Windows、macOS、Linux

## 首次使用
1. 启动应用后，在浏览器中打开 http://localhost:5000
2. 使用管理员账号登录：
   - 用户名：admin
   - 密码：admin123（首次登录后请修改）

## 功能模块
- ✅ 材料管理
- ✅ 采购询价
- ✅ 采购订单
- ✅ 库存管理
- ✅ 销售管理
- ✅ 对账管理
- ✅ 系统设置

## 技术栈
- **后端**：Flask + SQLite
- **前端**：HTML5 + JavaScript
- **数据库**：SQLite

## 常见问题

### Q: 启动后浏览器没有自动打开？
A: 手动打开浏览器，访问 http://localhost:5000

### Q: 端口被占用？
A: 修改 `app.py` 第71行的端口号，将 `port=5000` 改为其他端口（如 5001）

### Q: 数据库损坏？
A: 删除 `零星材管理系统.db` 文件，重新启动应用会自动创建新数据库

### Q: 忘记管理员密码？
A: 删除数据库文件或联系系统管理员重置

## 目录结构
```
零星材管理系统/
├── app.py                 # Flask 应用入口
├── config.py              # 配置文件
├── requirements.txt       # Python 依赖
├── 启动Web.bat           # Windows 启动脚本
├── blueprints/            # 业务模块蓝图
├── database/              # 数据库相关
├── helpers/               # 工具函数
├── services/             # 业务逻辑服务
├── static/                # 静态资源
└── views/                # PyQt5 视图（旧版桌面应用）
```

## 开发说明

### 数据库初始化
```python
from database.init_db import init_database, insert_default_data
init_database()
insert_default_data(conn)
```

### 添加新的蓝图模块
1. 在 `blueprints/` 目录下创建新模块
2. 在 `blueprints/__init__.py` 中导入
3. 在 `app.py` 中注册蓝图

## 许可证
内部使用系统

## 联系方式
技术支持：请联系系统管理员
