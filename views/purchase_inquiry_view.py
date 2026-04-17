"""
采购询价管理视图
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QDialog, QFormLayout,
    QLineEdit, QComboBox, QDoubleSpinBox, QTextEdit, QMessageBox,
    QHeaderView, QFrame, QGridLayout, QDateEdit
)
from PyQt5.QtCore import Qt, pyqtSignal, QDate
from PyQt5.QtGui import QFont

from database import get_connection
from services.purchase_inquiry_service import PurchaseInquiryService
from helpers import get_today


class PurchaseInquiryListView(QWidget):
    """采购询价列表视图"""

    navigate_to = pyqtSignal(str)

    def __init__(self, current_user: dict):
        super().__init__()
        self.current_user = current_user
        self.service = PurchaseInquiryService()
        self.current_inquiries = []
        self.init_ui()
        self.load_inquiries()

    def init_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #f0f2f5; }
            QLabel { color: #333; }
            QPushButton {
                background-color: #4a90e2; color: white; border: none;
                padding: 8px 16px; border-radius: 4px; font-size: 13px;
            }
            QPushButton:hover { background-color: #357abd; }
            QPushButton[secondary="true"] { background-color: #95a5a6; }
            QPushButton[secondary="true"]:hover { background-color: #7f8c8d; }
            QPushButton[danger="true"] { background-color: #e74c3c; }
            QPushButton[danger="true"]:hover { background-color: #c0392b; }
            QPushButton[success="true"] { background-color: #27ae60; }
            QPushButton[success="true"]:hover { background-color: #219a52; }
            QPushButton[warning="true"] { background-color: #f39c12; }
            QPushButton[warning="true"]:hover { background-color: #d68910; }
            QTableWidget {
                background-color: white; border: none; border-radius: 8px;
                gridline-color: #e0e0e0; font-size: 13px;
            }
            QTableWidget::item { padding: 5px; }
            QTableWidget::item:selected { background-color: #d6e6f7; color: #333; }
            QHeaderView::section {
                background-color: #f8f9fa; color: #333; font-size: 13px;
                font-weight: bold; padding: 8px; border: none;
                border-bottom: 2px solid #4a90e2;
            }
            QLineEdit, QComboBox {
                border: 1px solid #ddd; border-radius: 4px;
                padding: 6px 10px; font-size: 13px;
            }
            QFrame { background-color: white; border-radius: 8px; }
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title_label = QLabel("采购管理 - 询比价")
        title_label.setFont(QFont("微软雅黑", 18, QFont.Bold))
        main_layout.addWidget(title_label)

        main_layout.addSpacing(10)

        # 工具栏
        toolbar_frame = QFrame()
        toolbar_layout = QHBoxLayout()

        self.add_btn = QPushButton("新建询价单")
        self.add_btn.clicked.connect(self.on_create)

        self.view_btn = QPushButton("查看详情")
        self.view_btn.setProperty("secondary", True)
        self.view_btn.clicked.connect(self.on_view_detail)

        self.approve_btn = QPushButton("审批")
        self.approve_btn.setProperty("warning", True)
        self.approve_btn.clicked.connect(self.on_approve)

        self.print_btn = QPushButton("打印")
        self.print_btn.setProperty("secondary", True)
        self.print_btn.clicked.connect(self.on_print)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setProperty("secondary", True)
        self.refresh_btn.clicked.connect(self.load_inquiries)

        toolbar_layout.addWidget(self.add_btn)
        toolbar_layout.addWidget(self.view_btn)
        toolbar_layout.addWidget(self.approve_btn)
        toolbar_layout.addWidget(self.print_btn)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.refresh_btn)

        toolbar_frame.setLayout(toolbar_layout)
        main_layout.addWidget(toolbar_frame)

        main_layout.addSpacing(10)

        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "ID", "询价单号", "询价日期", "申请人",
            "总金额", "低于库内价", "审批状态", "创建时间"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        header.setSectionResizeMode(7, QHeaderView.Fixed)

        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 160)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 100)
        self.table.setColumnWidth(6, 120)
        self.table.setColumnWidth(7, 150)

        self.table.cellDoubleClicked.connect(self.on_view_detail)
        main_layout.addWidget(self.table)

        self.setLayout(main_layout)

    def load_inquiries(self):
        """加载询价单列表"""
        self.current_inquiries = self.service.get_all_inquiries()
        self._populate_table()

    def _populate_table(self):
        """填充表格"""
        self.table.setRowCount(len(self.current_inquiries))
        for row, inquiry in enumerate(self.current_inquiries):
            self.table.setItem(row, 0, QTableWidgetItem(str(inquiry.get("id", ""))))
            self.table.setItem(row, 1, QTableWidgetItem(inquiry.get("inquiry_no", "")))
            self.table.setItem(row, 2, QTableWidgetItem(inquiry.get("inquiry_date", "")))
            self.table.setItem(row, 3, QTableWidgetItem(inquiry.get("applicant_name", "")))
            self.table.setItem(row, 4, QTableWidgetItem(f"¥{inquiry.get('total_amount', 0):.2f}"))

            is_below = "是" if inquiry.get("is_below_library_price") == 1 else "否"
            self.table.setItem(row, 5, QTableWidgetItem(is_below))

            status = inquiry.get("approval_status", "")
            self.table.setItem(row, 6, QTableWidgetItem(status))

            # 根据状态设置颜色
            status_item = self.table.item(row, 6)
            if status == "待审批":
                status_item.setBackground(Qt.red)
                status_item.setForeground(Qt.white)
            elif status == "材料员已审":
                status_item.setBackground(Qt.yellow)
                status_item.setForeground(Qt.black)
            elif status == "已同意":
                status_item.setBackground(Qt.green)
                status_item.setForeground(Qt.white)
            elif status == "已驳回":
                status_item.setBackground(Qt.gray)
                status_item.setForeground(Qt.white)

            self.table.setItem(row, 7, QTableWidgetItem(inquiry.get("create_time", "")[:19] if inquiry.get("create_time") else ""))

            for col in range(8):
                item = self.table.item(row, col)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)

    def on_create(self):
        """新建询价单"""
        dialog = PurchaseInquiryCreateDialog(self, self.current_user)
        if dialog.exec_() == QDialog.Accepted:
            self.load_inquiries()

    def on_view_detail(self):
        """查看详情"""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请选择要查看的询价单")
            return

        inquiry_id = int(self.table.item(row, 0).text())
        dialog = PurchaseInquiryDetailDialog(self, inquiry_id, self.current_user)
        dialog.exec_()

    def on_approve(self):
        """审批"""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请选择要审批的询价单")
            return

        inquiry_id = int(self.table.item(row, 0).text())
        status = self.table.item(row, 6).text()

        if status == "已同意":
            QMessageBox.information(self, "提示", "该询价单已审批通过")
            return
        if status == "已驳回":
            QMessageBox.information(self, "提示", "该询价单已被驳回")
            return

        dialog = PurchaseInquiryApproveDialog(self, inquiry_id, status, self.current_user)
        if dialog.exec_() == QDialog.Accepted:
            self.load_inquiries()

    def on_print(self):
        """打印"""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请选择要打印的询价单")
            return

        inquiry_id = int(self.table.item(row, 0).text())
        QMessageBox.information(self, "提示", f"打印功能开发中...\n询价单ID: {inquiry_id}")


class PurchaseInquiryCreateDialog(QDialog):
    """新建询价单对话框"""

    def __init__(self, parent, current_user):
        super().__init__(parent)
        self.current_user = current_user
        self.materials = []
        self.suppliers = []
        self.details = []
        self.init_ui()
        self.load_materials_and_suppliers()

    def init_ui(self):
        self.setWindowTitle("新建询价单")
        self.setMinimumSize(900, 600)
        self.setStyleSheet("""
            QDialog { background-color: #f0f2f5; }
            QLabel { color: #333; font-size: 13px; }
            QPushButton {
                background-color: #4a90e2; color: white; border: none;
                padding: 8px 16px; border-radius: 4px; font-size: 13px;
            }
            QPushButton:hover { background-color: #357abd; }
            QPushButton[cancel="true"] { background-color: #95a5a6; }
            QPushButton[cancel="true"]:hover { background-color: #7f8c8d; }
            QPushButton[danger="true"] { background-color: #e74c3c; }
            QPushButton[danger="true"]:hover { background-color: #c0392b; }
            QTableWidget {
                background-color: white; border: 1px solid #ddd;
                gridline-color: #e0e0e0; font-size: 13px;
            }
            QLineEdit, QComboBox, QTextEdit {
                border: 1px solid #ddd; border-radius: 4px;
                padding: 6px; font-size: 13px;
            }
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 10)

        # 基本信息区
        info_frame = QFrame()
        info_layout = QHBoxLayout()

        # 询价日期
        date_layout = QVBoxLayout()
        date_layout.addWidget(QLabel("询价日期:"))
        self.date_input = QDateEdit(QDate.currentDate())
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("yyyy-MM-dd")
        date_layout.addWidget(self.date_input)
        info_layout.addLayout(date_layout)

        # 备注
        remark_layout = QVBoxLayout()
        remark_layout.addWidget(QLabel("备注:"))
        self.remark_input = QTextEdit()
        self.remark_input.setMaximumHeight(60)
        self.remark_input.setPlaceholderText("请输入备注信息")
        remark_layout.addWidget(self.remark_input)
        info_layout.addLayout(remark_layout)

        info_frame.setLayout(info_layout)
        main_layout.addWidget(info_frame)

        main_layout.addSpacing(10)

        # 添加明细区
        add_frame = QFrame()
        add_layout = QGridLayout()

        # 材料选择
        add_layout.addWidget(QLabel("材料:"), 0, 0)
        self.material_combo = QComboBox()
        self.material_combo.setMinimumWidth(200)
        add_layout.addWidget(self.material_combo, 0, 1)

        # 供应商选择
        add_layout.addWidget(QLabel("供应商:"), 0, 2)
        self.supplier_combo = QComboBox()
        self.supplier_combo.setMinimumWidth(150)
        add_layout.addWidget(self.supplier_combo, 0, 3)

        # 本次报价
        add_layout.addWidget(QLabel("含税报价:"), 0, 4)
        self.price_input = QDoubleSpinBox()
        self.price_input.setRange(0, 99999999)
        self.price_input.setDecimals(2)
        self.price_input.setSuffix(" 元")
        add_layout.addWidget(self.price_input, 0, 5)

        # 数量
        add_layout.addWidget(QLabel("数量:"), 0, 6)
        self.quantity_input = QDoubleSpinBox()
        self.quantity_input.setRange(1, 999999)
        self.quantity_input.setDecimals(2)
        self.quantity_input.setValue(1)
        add_layout.addWidget(self.quantity_input, 0, 7)

        # 添加按钮
        self.add_detail_btn = QPushButton("添加")
        self.add_detail_btn.clicked.connect(self.on_add_detail)
        add_layout.addWidget(self.add_detail_btn, 0, 8)

        add_frame.setLayout(add_layout)
        main_layout.addWidget(add_frame)

        # 明细表格
        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(8)
        self.detail_table.setHorizontalHeaderLabels([
            "材料编码", "材料名称", "规格", "供应商", "库内价", "本次报价", "数量", "操作"
        ])
        self.detail_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.detail_table.verticalHeader().setVisible(False)
        self.detail_table.setColumnWidth(0, 100)
        self.detail_table.setColumnWidth(1, 150)
        self.detail_table.setColumnWidth(2, 120)
        self.detail_table.setColumnWidth(3, 120)
        self.detail_table.setColumnWidth(4, 80)
        self.detail_table.setColumnWidth(5, 80)
        self.detail_table.setColumnWidth(6, 60)
        self.detail_table.setColumnWidth(7, 60)
        main_layout.addWidget(self.detail_table)

        # 总金额显示
        total_layout = QHBoxLayout()
        total_layout.addStretch()
        self.total_label = QLabel("总金额: ¥0.00")
        self.total_label.setFont(QFont("微软雅黑", 12, QFont.Bold))
        total_layout.addWidget(self.total_label)
        main_layout.addLayout(total_layout)

        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setProperty("cancel", True)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        submit_btn = QPushButton("提交询价")
        submit_btn.clicked.connect(self.on_submit)
        btn_layout.addWidget(submit_btn)

        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def load_materials_and_suppliers(self):
        """加载材料和供应商"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT m.id, m.material_code, m.material_name, m.specification,
                   m.tax_price, u.unit_name
            FROM materials m
            LEFT JOIN units u ON m.unit_id = u.id
            ORDER BY m.material_code
        """)
        self.materials = cursor.fetchall()

        cursor.execute("SELECT id, supplier_name FROM suppliers ORDER BY supplier_name")
        self.suppliers = cursor.fetchall()

        conn.close()

        # 填充材料下拉框
        self.material_combo.clear()
        for m in self.materials:
            self.material_combo.addItem(f"{m['material_code']} - {m['material_name']}", m['id'])

        # 填充供应商下拉框
        self.supplier_combo.clear()
        for s in self.suppliers:
            self.supplier_combo.addItem(s['supplier_name'], s['id'])

    def on_add_detail(self):
        """添加明细"""
        material_id = self.material_combo.currentData()
        if not material_id:
            QMessageBox.warning(self, "提示", "请选择材料")
            return

        supplier_id = self.supplier_combo.currentData()
        if not supplier_id:
            QMessageBox.warning(self, "提示", "请选择供应商")
            return

        price = self.price_input.value()
        if price <= 0:
            QMessageBox.warning(self, "提示", "请输入有效的报价")
            return

        quantity = self.quantity_input.value()

        # 获取材料信息
        material = next((m for m in self.materials if m['id'] == material_id), None)
        supplier = next((s for s in self.suppliers if s['id'] == supplier_id), None)

        # 检查是否已添加
        for d in self.details:
            if d['material_id'] == material_id and d['supplier_id'] == supplier_id:
                QMessageBox.warning(self, "提示", "该材料已添加，请编辑或删除后重新添加")
                return

        # 添加到明细
        self.details.append({
            'material_id': material_id,
            'supplier_id': supplier_id,
            'this_price': price,
            'library_price': material['tax_price'] if material else 0,
            'quantity': quantity,
            'material_code': material['material_code'] if material else '',
            'material_name': material['material_name'] if material else '',
            'specification': material['specification'] if material else '',
            'supplier_name': supplier['supplier_name'] if supplier else ''
        })

        self._refresh_detail_table()

    def _refresh_detail_table(self):
        """刷新明细表格"""
        self.detail_table.setRowCount(len(self.details))
        for row, d in enumerate(self.details):
            self.detail_table.setItem(row, 0, QTableWidgetItem(d.get('material_code', '')))
            self.detail_table.setItem(row, 1, QTableWidgetItem(d.get('material_name', '')))
            self.detail_table.setItem(row, 2, QTableWidgetItem(d.get('specification', '')))
            self.detail_table.setItem(row, 3, QTableWidgetItem(d.get('supplier_name', '')))
            self.detail_table.setItem(row, 4, QTableWidgetItem(f"¥{d.get('library_price', 0):.2f}"))
            self.detail_table.setItem(row, 5, QTableWidgetItem(f"¥{d.get('this_price', 0):.2f}"))
            self.detail_table.setItem(row, 6, QTableWidgetItem(str(d.get('quantity', 1))))

            del_btn = QPushButton("删除")
            del_btn.setProperty("danger", True)
            del_btn.clicked.connect(lambda _, r=row: self.on_delete_detail(r))
            self.detail_table.setCellWidget(row, 7, del_btn)

            for col in range(8):
                item = self.detail_table.item(row, col)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)

        # 更新总金额
        total = sum(d.get('this_price', 0) * d.get('quantity', 1) for d in self.details)
        self.total_label.setText(f"总金额: ¥{total:.2f}")

    def on_delete_detail(self, row):
        """删除明细"""
        if 0 <= row < len(self.details):
            del self.details[row]
            self._refresh_detail_table()

    def on_submit(self):
        """提交询价单"""
        if not self.details:
            QMessageBox.warning(self, "提示", "请添加询价明细")
            return

        inquiry_data = {
            'inquiry_date': self.date_input.date().toString("yyyy-MM-dd"),
            'remark': self.remark_input.toPlainText()
        }

        service = PurchaseInquiryService()
        result = service.create_inquiry(inquiry_data, self.details, self.current_user['id'])

        if result.get('success'):
            QMessageBox.information(self, "成功", f"询价单创建成功！\n单号: {result.get('inquiry_no')}")
            self.accept()
        else:
            QMessageBox.warning(self, "失败", result.get('message', '创建失败'))


class PurchaseInquiryDetailDialog(QDialog):
    """询价单详情对话框"""

    def __init__(self, parent, inquiry_id, current_user):
        super().__init__(parent)
        self.inquiry_id = inquiry_id
        self.current_user = current_user
        self.service = PurchaseInquiryService()
        self.init_ui()
        self.load_data()

    def init_ui(self):
        self.setWindowTitle("询价单详情")
        self.setMinimumSize(800, 500)
        self.setStyleSheet("""
            QDialog { background-color: #f0f2f5; }
            QLabel { color: #333; font-size: 13px; }
            QTableWidget {
                background-color: white; border: 1px solid #ddd;
                gridline-color: #e0e0e0; font-size: 13px;
            }
            QHeaderView::section {
                background-color: #f8f9fa; color: #333; font-size: 13px;
                font-weight: bold; padding: 6px; border: none;
                border-bottom: 1px solid #ddd;
            }
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 10)

        # 基本信息
        info_frame = QFrame()
        info_layout = QFormLayout()
        info_layout.setLabelWidth(80)

        self.no_label = QLabel()
        self.date_label = QLabel()
        self.applicant_label = QLabel()
        self.status_label = QLabel()
        self.total_label = QLabel()
        self.below_library_label = QLabel()
        self.remark_label = QLabel()

        info_layout.addRow("询价单号:", self.no_label)
        info_layout.addRow("询价日期:", self.date_label)
        info_layout.addRow("申请人:", self.applicant_label)
        info_layout.addRow("审批状态:", self.status_label)
        info_layout.addRow("总金额:", self.total_label)
        info_layout.addRow("低于库内价:", self.below_library_label)
        info_layout.addRow("备注:", self.remark_label)

        info_frame.setLayout(info_layout)
        main_layout.addWidget(info_frame)

        main_layout.addSpacing(10)

        # 明细表格
        main_layout.addWidget(QLabel("询价明细:"))
        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(9)
        self.detail_table.setHorizontalHeaderLabels([
            "材料编码", "材料名称", "规格", "单位", "供应商",
            "库内价", "本次报价", "价差", "最低价"
        ])
        self.detail_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.detail_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.detail_table.verticalHeader().setVisible(False)
        self.detail_table.setColumnWidth(0, 100)
        self.detail_table.setColumnWidth(1, 150)
        self.detail_table.setColumnWidth(2, 100)
        self.detail_table.setColumnWidth(3, 60)
        self.detail_table.setColumnWidth(4, 120)
        self.detail_table.setColumnWidth(5, 80)
        self.detail_table.setColumnWidth(6, 80)
        self.detail_table.setColumnWidth(7, 80)
        self.detail_table.setColumnWidth(8, 60)
        main_layout.addWidget(self.detail_table)

        # 关闭按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)
        main_layout.addLayout(btn_layout)

        self.setLayout(main_layout)

    def load_data(self):
        """加载数据"""
        inquiry = self.service.get_inquiry_by_id(self.inquiry_id)
        if not inquiry:
            return

        self.no_label.setText(inquiry.get('inquiry_no', ''))
        self.date_label.setText(inquiry.get('inquiry_date', ''))
        self.applicant_label.setText(inquiry.get('applicant_name', ''))
        self.status_label.setText(inquiry.get('approval_status', ''))
        self.total_label.setText(f"¥{inquiry.get('total_amount', 0):.2f}")
        self.below_library_label.setText("是" if inquiry.get('is_below_library_price') == 1 else "否")
        self.remark_label.setText(inquiry.get('remark') or '-')

        # 加载明细
        details = self.service.get_inquiry_details(self.inquiry_id)
        self.detail_table.setRowCount(len(details))
        for row, d in enumerate(details):
            self.detail_table.setItem(row, 0, QTableWidgetItem(d.get('material_code', '')))
            self.detail_table.setItem(row, 1, QTableWidgetItem(d.get('material_name', '')))
            self.detail_table.setItem(row, 2, QTableWidgetItem(d.get('specification', '')))
            self.detail_table.setItem(row, 3, QTableWidgetItem(d.get('unit_name', '')))
            self.detail_table.setItem(row, 4, QTableWidgetItem(d.get('supplier_name', '')))
            self.detail_table.setItem(row, 5, QTableWidgetItem(f"¥{d.get('library_price', 0):.2f}"))
            self.detail_table.setItem(row, 6, QTableWidgetItem(f"¥{d.get('this_price', 0):.2f}"))
            self.detail_table.setItem(row, 7, QTableWidgetItem(f"¥{d.get('price_diff', 0):.2f}"))
            self.detail_table.setItem(row, 8, QTableWidgetItem("是" if d.get('is_lowest') == 1 else "否"))

            for col in range(9):
                item = self.detail_table.item(row, col)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)


class PurchaseInquiryApproveDialog(QDialog):
    """询价单审批对话框"""

    def __init__(self, parent, inquiry_id, current_status, current_user):
        super().__init__(parent)
        self.inquiry_id = inquiry_id
        self.current_status = current_status
        self.current_user = current_user
        self.service = PurchaseInquiryService()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("审批询价单")
        self.setFixedSize(400, 300)
        self.setStyleSheet("""
            QDialog { background-color: #f0f2f5; }
            QLabel { color: #333; font-size: 13px; }
            QPushButton {
                background-color: #4a90e2; color: white; border: none;
                padding: 10px 20px; border-radius: 4px; font-size: 13px;
            }
            QPushButton:hover { background-color: #357abd; }
            QPushButton[cancel="true"] { background-color: #95a5a6; }
            QPushButton[cancel="true"]:hover { background-color: #7f8c8d; }
            QPushButton[success="true"] { background-color: #27ae60; }
            QPushButton[success="true"]:hover { background-color: #219a52; }
            QPushButton[danger="true"] { background-color: #e74c3c; }
            QPushButton[danger="true"]:hover { background-color: #c0392b; }
            QTextEdit {
                border: 1px solid #ddd; border-radius: 4px;
                padding: 8px; font-size: 13px;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 10)

        # 状态显示
        status_text = {
            "待审批": "材料员审批",
            "材料员已审": "主管审批"
        }
        layout.addWidget(QLabel(f"当前状态: {self.current_status}"))
        layout.addWidget(QLabel(f"即将进行: {status_text.get(self.current_status, '审批')}"))

        layout.addSpacing(10)

        # 审批意见
        layout.addWidget(QLabel("审批意见:"))
        self.remark_input = QTextEdit()
        self.remark_input.setPlaceholderText("请输入审批意见（选填）")
        layout.addWidget(self.remark_input)

        layout.addStretch()

        # 按钮
        btn_layout = QHBoxLayout()

        reject_btn = QPushButton("驳回")
        reject_btn.setProperty("danger", True)
        reject_btn.clicked.connect(self.on_reject)

        approve_btn = QPushButton("同意")
        approve_btn.setProperty("success", True)
        approve_btn.clicked.connect(self.on_approve)

        cancel_btn = QPushButton("取消")
        cancel_btn.setProperty("cancel", True)
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(reject_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(approve_btn)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def on_approve(self):
        """同意"""
        remark = self.remark_input.toPlainText().strip()

        if self.current_status == "待审批":
            # 材料员审批
            result = self.service.approve_by_material_clerk(
                self.inquiry_id, self.current_user['id'], remark
            )
        else:
            # 主管审批
            result = self.service.approve_by_manager(
                self.inquiry_id, self.current_user['id'], remark
            )

        if result.get('success'):
            QMessageBox.information(self, "成功", "审批成功！")
            self.accept()
        else:
            QMessageBox.warning(self, "失败", result.get('message', '审批失败'))

    def on_reject(self):
        """驳回"""
        remark = self.remark_input.toPlainText().strip()
        if not remark:
            QMessageBox.warning(self, "提示", "请输入驳回原因")
            return

        result = self.service.reject(self.inquiry_id, self.current_user['id'], remark)
        if result.get('success'):
            QMessageBox.information(self, "成功", "已驳回！")
            self.accept()
        else:
            QMessageBox.warning(self, "失败", result.get('message', '驳回失败'))
