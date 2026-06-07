"""
蓝图模块
"""
from .auth import auth_bp
from .materials import material_bp
from .inquiries import inquiry_bp
from .stock import stock_bp
from .sales import sales_bp
from .reconciliation import reconciliation_bp
from .system import system_bp
from .dashboard import dashboard_bp
from .owner_supplied import owner_supplied_bp
from .transfers import transfer_bp

__all__ = [
    'auth_bp',
    'material_bp',
    'inquiry_bp',
    'stock_bp',
    'sales_bp',
    'reconciliation_bp',
    'system_bp',
    'dashboard_bp',
    'owner_supplied_bp',
    'transfer_bp',
]
