"""
数据模型
所有数据库表的 Python 对象表示
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


@dataclass
class User:
    id: Optional[int] = None
    username: str = ""
    password: str = ""
    real_name: str = ""
    role_id: Optional[int] = None
    is_active: int = 1
    create_time: Optional[str] = None


@dataclass
class Role:
    id: Optional[int] = None
    role_name: str = ""
    permissions: str = ""  # JSON 格式


@dataclass
class Warehouse:
    id: Optional[int] = None
    warehouse_name: str = ""
    address: str = ""
    remark: str = ""
    is_default: int = 0
    create_time: Optional[str] = None


@dataclass
class Supplier:
    id: Optional[int] = None
    supplier_name: str = ""
    contact: str = ""
    phone: str = ""
    address: str = ""
    remark: str = ""
    create_time: Optional[str] = None


@dataclass
class SupplierAccount:
    id: Optional[int] = None
    supplier_id: Optional[int] = None
    username: str = ""
    password: str = ""
    status: str = "pending"  # pending / active / disabled
    is_active: int = 0
    create_time: Optional[str] = None
    last_login_time: Optional[str] = None


@dataclass
class Unit:
    id: Optional[int] = None
    unit_name: str = ""
    unit_code: str = ""


@dataclass
class Material:
    id: Optional[int] = None
    material_code: str = ""
    material_name: str = ""
    specification: str = ""
    detail_spec: str = ""  # 详细规格
    is_national_standard: int = 0  # 是否国标 (0=否, 1=是)
    brand: str = ""  # 品牌
    unit_id: Optional[int] = None
    tax_price: float = 0.0  # 含税价
    tax_exempt_price: float = 0.0  # 不含税价
    is_cash_price: int = 0  # 是否现金含税价 (0=否, 1=是)
    cash_price: float = 0.0  # 现金含税价（不含税）
    cash_tax_price: float = 0.0  # 现金不含税价
    freight: float = 0.0
    remark: str = ""
    default_supplier_id: Optional[int] = None
    inventory_min: float = 0.0  # 库存下限
    inventory_max: float = 0.0  # 库存上限
    create_time: Optional[str] = None


@dataclass
class MaterialPriceHistory:
    id: Optional[int] = None
    material_id: Optional[int] = None
    supplier_id: Optional[int] = None
    tax_price: float = 0.0
    inquired_time: Optional[str] = None
    inquired_by: Optional[int] = None
    inquiry_id: Optional[int] = None


@dataclass
class Inventory:
    id: Optional[int] = None
    material_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    quantity: float = 0.0
    unit_price: float = 0.0  # 库内单价（含税）
    update_time: Optional[str] = None


@dataclass
class Project:
    id: Optional[int] = None
    project_code: str = ""
    project_name: str = ""
    contract_no: str = ""
    customer_id: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    remark: str = ""
    create_time: Optional[str] = None


@dataclass
class Customer:
    id: Optional[int] = None
    customer_code: str = ""
    customer_name: str = ""
    address: str = ""
    phone: str = ""
    contact: str = ""
    initial_balance: float = 0.0  # 期初余额
    remark: str = ""
    create_time: Optional[str] = None


@dataclass
class PurchaseInquiry:
    id: Optional[int] = None
    inquiry_no: str = ""  # CGXJ-YYMMDD-XXX
    inquiry_date: Optional[str] = None
    applicant_id: Optional[int] = None
    total_amount: float = 0.0
    is_below_library_price: int = 0  # 是否低于库内价
    approval_status: str = "待审批"  # 待审批/材料员已审/已同意/已驳回
    approval_remark: str = ""
    approver_id: Optional[int] = None
    approve_time: Optional[str] = None
    library_price_updated: int = 0  # 库内价是否已更新
    quote_status: str = "draft"  # draft / collecting / locked
    quote_deadline: Optional[str] = None
    create_time: Optional[str] = None
    remark: str = ""


@dataclass
class PurchaseInquiryDetail:
    id: Optional[int] = None
    inquiry_id: Optional[int] = None
    material_id: Optional[int] = None
    supplier_id: Optional[int] = None
    this_price: float = 0.0  # 本次报价（含税）
    library_price: float = 0.0  # 库内价（快照）
    is_lowest: int = 0  # 是否为最低价
    price_diff: float = 0.0  # 与库内价差额


@dataclass
class PurchaseInquiryItem:
    """询价单材料项分组"""
    id: Optional[int] = None
    inquiry_id: Optional[int] = None
    material_id: Optional[int] = None
    quantity: float = 1.0  # 采购数量
    library_price: float = 0.0  # 库内价（快照）
    selected_quote_id: Optional[int] = None  # 选定的报价ID
    is_national_standard: int = 0  # 是否国标
    is_cash_price: int = 0  # 是否现金含税价
    create_time: Optional[str] = None
    # 关联数据（API返回用，不存库）
    material_name: str = ""
    material_code: str = ""
    specification: str = ""
    unit_name: str = ""


@dataclass
class PurchaseInquiryQuote:
    """询价单各家报价"""
    id: Optional[int] = None
    item_id: Optional[int] = None
    supplier_id: Optional[int] = None
    tax_price: float = 0.0  # 含税单价
    tax_exempt_price: float = 0.0  # 不含税单价
    tax_rate: float = 0.13  # 税率
    total_amount: float = 0.0  # 报价总金额 = tax_price * quantity
    is_lowest: int = 0  # 是否为最低价（1=是，0=否）
    is_selected: int = 0  # 是否被选定为推荐供应商
    quote_status: str = "pending"  # pending / saved / submitted / locked
    submitted_at: Optional[str] = None
    updated_at: Optional[str] = None
    supplier_remark: str = ""
    create_time: Optional[str] = None
    # 关联数据
    supplier_name: str = ""


@dataclass
class PurchaseOrder:
    id: Optional[int] = None
    order_no: str = ""  # CGDD-YYMMDD-XXX
    order_type: str = "集采"  # 零采/集采
    project_id: Optional[int] = None
    supplier_id: Optional[int] = None
    total_amount: float = 0.0
    applicant_id: Optional[int] = None
    approval_status: str = "待审批"
    approval_remark: str = ""
    approver_id: Optional[int] = None
    approve_time: Optional[str] = None
    purchase_status: str = "待入库"
    create_time: Optional[str] = None
    remark: str = ""


@dataclass
class PurchaseOrderDetail:
    id: Optional[int] = None
    order_id: Optional[int] = None
    material_id: Optional[int] = None
    quantity: float = 0.0
    unit_price: float = 0.0
    amount: float = 0.0
    in_quantity: float = 0.0  # 已入库数量


@dataclass
class StockInOrder:
    id: Optional[int] = None
    order_no: str = ""  # JH-YYMMDD-XXX
    source_type: str = "采购入库"  # 采购入库/退货入库
    related_order_no: str = ""  # 关联单号
    supplier_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    operator_id: Optional[int] = None
    in_time: Optional[str] = None
    status: str = "已入库"
    create_time: Optional[str] = None
    remark: str = ""


@dataclass
class StockInDetail:
    id: Optional[int] = None
    order_id: Optional[int] = None
    material_id: Optional[int] = None
    quantity: float = 0.0
    unit_price: float = 0.0
    amount: float = 0.0
    supplier_id: Optional[int] = None


@dataclass
class StockOutOrder:
    id: Optional[int] = None
    order_no: str = ""  # CK-YYMMDD-XXX
    out_type: str = "领用"  # 领用/零售/批发
    customer_name: str = ""
    warehouse_id: Optional[int] = None
    operator_id: Optional[int] = None
    out_time: Optional[str] = None
    create_time: Optional[str] = None
    remark: str = ""


@dataclass
class StockOutDetail:
    id: Optional[int] = None
    order_id: Optional[int] = None
    material_id: Optional[int] = None
    quantity: float = 0.0
    unit_price: float = 0.0
    amount: float = 0.0


@dataclass
class StockTransferOrder:
    id: Optional[int] = None
    transfer_no: str = ""  # DB-YYMMDD-XXX
    from_warehouse_id: Optional[int] = None
    to_warehouse_id: Optional[int] = None
    operator_id: Optional[int] = None
    transfer_time: Optional[str] = None
    create_time: Optional[str] = None
    remark: str = ""


@dataclass
class StockTransferDetail:
    id: Optional[int] = None
    order_id: Optional[int] = None
    material_id: Optional[int] = None
    quantity: float = 0.0
    unit_price: float = 0.0
    amount: float = 0.0


@dataclass
class SalesOrder:
    id: Optional[int] = None
    order_no: str = ""  # XS-YYMMDD-XXXX
    order_type: str = "零售"  # 零售/批发
    customer_id: Optional[int] = None
    customer_name: str = ""
    total_amount: float = 0.0
    received_amount: float = 0.0
    payment_status: str = "未付款"  # 未付款/部分付款/已结清
    print_count: int = 0
    salesperson_id: Optional[int] = None
    create_time: Optional[str] = None
    remark: str = ""


@dataclass
class SalesOrderDetail:
    id: Optional[int] = None
    order_id: Optional[int] = None
    material_id: Optional[int] = None
    quantity: float = 0.0
    unit_price: float = 0.0
    discount: float = 1.0  # 折扣
    amount: float = 0.0


@dataclass
class ReconciliationStatement:
    id: Optional[int] = None
    statement_no: str = ""  # DZD-YYYY.N.N~YYYY.N.N
    project_id: Optional[int] = None
    supplier_id: Optional[int] = None
    customer_id: Optional[int] = None
    contract_no: str = ""
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    total_amount: float = 0.0  # 本期结算金额（含税）
    tax_rate: float = 0.01
    tax_exempt_amount: float = 0.0  # 本期不含税金额
    total_paid: float = 0.0  # 累计已付款
    total_invoiced: float = 0.0  # 累计已开票
    total_received: float = 0.0  # 累计已收款
    balance_due: float = 0.0  # 截止本次尚欠
    status: str = "草稿"
    print_count: int = 0
    create_time: Optional[str] = None
    remark: str = ""


@dataclass
class ReconciliationDetail:
    id: Optional[int] = None
    statement_id: Optional[int] = None
    original_no: str = ""  # 原始单号
    transaction_date: Optional[str] = None
    material_id: Optional[int] = None
    specification: str = ""
    unit_id: Optional[int] = None
    quantity: float = 0.0
    unit_price: float = 0.0
    amount: float = 0.0
    remark: str = ""


@dataclass
class ApprovalRecord:
    id: Optional[int] = None
    order_type: str = ""  # purchase_inquiry / purchase_order
    order_id: Optional[int] = None
    approver_id: Optional[int] = None
    approver_name: str = ""
    result: str = ""  # 同意/驳回
    remark: str = ""
    approval_time: Optional[str] = None


@dataclass
class OperationLog:
    id: Optional[int] = None
    user_id: Optional[int] = None
    module: str = ""
    action: str = ""
    target_id: Optional[int] = None
    detail: str = ""
    create_time: Optional[str] = None


@dataclass
class UserProject:
    """用户-项目多对多关联"""
    id: Optional[int] = None
    user_id: Optional[int] = None
    project_id: Optional[int] = None
