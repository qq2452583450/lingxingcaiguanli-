"""
配置文件
"""
import os

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据库路径
DATABASE_PATH = os.path.join(BASE_DIR, "零星材管理系统.db")

# 系统名称
SYSTEM_NAME = "零星材管理系统"

# 公司信息（打印用）
COMPANY_NAME = "XXX贸易有限公司"
COMPANY_ADDRESS = "XX区XX路XX号"
COMPANY_PHONE = "010-12345678"

# 单号格式
# 入库单: JH-YYMMDD-001
# 销售单: XS-YYMMDD-0001
# 询价单: CGXJ-YYMMDD-001
# 对账单: DZD-YYYY.N.N~YYYY.N.N

# 预置计量单位
DEFAULT_UNITS = [
    "米", "根", "吨", "卷", "块", "个", "箱", "套", "片", "盒", "张"
]

# 预置角色
DEFAULT_ROLES = [
    {"name": "系统管理员", "permissions": "*"},
    {"name": "材料员", "permissions": "material.view,material.add,material.edit,stock.in,stock.out,stock.view,inventory.view"},
]

# 预置账号（密码通过环境变量 ADMIN_PASSWORD 设置，默认为空，首次登录需修改）
DEFAULT_ADMIN = {
    "username": "admin",
    "password": os.environ.get('ADMIN_PASSWORD', ''),
    "real_name": "系统管理员",
    "role": "系统管理员"
}

# 税率（默认 1%）
DEFAULT_TAX_RATE = 0.01
