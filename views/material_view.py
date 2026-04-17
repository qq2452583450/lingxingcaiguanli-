"""
材料信息管理视图
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDoubleSpinBox,
    QTextEdit, QMessageBox, QHeaderView, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from database import get_connection
from database.models import Material
from services.material_service import MaterialService


class MaterialListView(QWidget):
    """材料列表视图"""

    navigate_to = pyqtSignal(str)

    def __init__(self, current_user: dict):
        super().__init__()
        self.current_user = current_user
        self.material_service = MaterialService()
        self.current_materials = []
        self.init_ui()
        self.load_materials()

    def init_ui(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #f0f2f5;
            }
            QLabel {
                color: #333;
            }
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton[secondary="true"] {
                background-color: #95a5a6;
            }
            QPushButton[secondary="true"]:hover {
                background-color: #7f8c8d;
            }
            QPushButton[danger="true"] {
                background-color: #e74c3c;
            }
            QPushButton[danger="true"]:hover {
                background-color: #c0392b;
            }
            QTableWidget {
                background-color: white;
                border: none;
                border-radius: 8px;
                gridline-color: #e0e0e0;
                font-size: 13px;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #d6e6f7;
                color: #333;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                color: #333;
                font-size: 13px;
                font-weight: bold;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #4a90e2;
            }
            QLineEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #4a90e2;
            }
            QComboBox {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QFrame {
                background-color: white;
                border-radius: 8px;
            }
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 顶部标题区
        title_frame = QFrame()
        title_layout = QHBoxLayout()
        title_label = QLabel("材料信息管理")
        title_label.setFont(QFont("微软雅黑", 18, QFont.Bold))
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        # 搜索区
        search_frame = QFrame()
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(10, 10, 10, 10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入材料名称、编码或规格进行搜索")
        self.search_input.setFixedWidth(300)
        self.search_input.returnPressed.connect(self.on_search)

        search_btn = QPushButton("搜索")
        search_btn.setFixedWidth(80)
        search_btn.clicked.connect(self.on_search)

        self.add_btn = QPushButton("新建材料")
        self.add_btn.setFixedWidth(100)
        self.add_btn.clicked.connect(self.on_add)

        self.edit_btn = QPushButton("编辑")
        self.edit_btn.setFixedWidth(80)
        self.edit_btn.setProperty("secondary", True)
        self.edit_btn.clicked.connect(self.on_edit)

        self.delete_btn = QPushButton("删除")
        self.delete_btn.setFixedWidth(80)
        self.delete_btn.setProperty("danger", True)
        self.delete_btn.clicked.connect(self.on_delete)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setFixedWidth(80)
        self.refresh_btn.setProperty("secondary", True)
        self.refresh_btn.clicked.connect(self.load_materials)

        search_layout.addWidget(self.search_input)
        search_layout.addWidget(search_btn)
        search_layout.addStretch()
        search_layout.addWidget(self.add_btn)
        search_layout.addWidget(self.edit_btn)
        search_layout.addWidget(self.delete_btn)
        search_layout.addWidget(self.refresh_btn)

        search_frame.setLayout(search_layout)

        # 表格区
        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels([
            "ID", "材料编码", "材料名称", "规格", "单位",
            "含税价", "不含税价", "运费", "默认供应商",
            "库存下限", "库存上限"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)

        # 设置列宽
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        header.setSectionResizeMode(7, QHeaderView.Fixed)
        header.setSectionResizeMode(8, QHeaderView.Fixed)
        header.setSectionResizeMode(9, QHeaderView.Fixed)
        header.setSectionResizeMode(10, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(4, 60)
        self.table.setColumnWidth(5, 100)
        self.table.setColumnWidth(6, 100)
        self.table.setColumnWidth(7, 80)
        self.table.setColumnWidth(8, 120)
        self.table.setColumnWidth(9, 80)
        self.table.setColumnWidth(10, 80)

        self.table.cellDoubleClicked.connect(self.on_edit)

        main_layout.addWidget(title_label)
        main_layout.addSpacing(10)
        main_layout.addWidget(search_frame)
        main_layout.addSpacing(10)
        main_layout.addWidget(self.table)

        self.setLayout(main_layout)

    def load_materials(self):
        """加载材料列表"""
        self.current_materials = self.material_service.get_all_materials()
        self._populate_table()

    def on_search(self):
        """搜索材料"""
        keyword = self.search_input.text().strip()
        if keyword:
            self.current_materials = self.material_service.search_materials(keyword)
        else:
            self.current_materials = self.material_service.get_all_materials()
        self._populate_table()

    def _populate_table(self):
        """填充表格"""
        self.table.setRowCount(len(self.current_materials))
        for row, material in enumerate(self.current_materials):
            self.table.setItem(row, 0, QTableWidgetItem(str(material.get("id", ""))))
            self.table.setItem(row, 1, QTableWidgetItem(material.get("material_code", "")))
            self.table.setItem(row, 2, QTableWidgetItem(material.get("material_name", "")))
            self.table.setItem(row, 3, QTableWidgetItem(material.get("specification", "")))
            self.table.setItem(row, 4, QTableWidgetItem(material.get("unit_name", "")))
            self.table.setItem(row, 5, QTableWidgetItem(f"¥{material.get('tax_price', 0):.2f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"¥{material.get('tax_exempt_price', 0):.2f}"))
            self.table.setItem(row, 7, QTableWidgetItem(f"¥{material.get('freight', 0):.2f}"))
            self.table.setItem(row, 8, QTableWidgetItem(material.get("supplier_name", "") or "-"))
            self.table.setItem(row, 9, QTableWidgetItem(str(material.get("inventory_min", 0))))
            self.table.setItem(row, 10, QTableWidgetItem(str(material.get("inventory_max", 0))))

            # 居中对齐
            for col in range(11):
                item = self.table.item(row, col)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)

    def on_add(self):
        """新建材料"""
        dialog = MaterialEditDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.load_materials()

    def on_edit(self):
        """编辑材料"""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请选择要编辑的材料")
            return

        material_id = int(self.table.item(row, 0).text())
        material = self.material_service.get_material_by_id(material_id)
        if not material:
            QMessageBox.warning(self, "错误", "未找到该材料")
            return

        dialog = MaterialEditDialog(self, material)
        if dialog.exec_() == QDialog.Accepted:
            self.load_materials()

    def on_delete(self):
        """删除材料"""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请选择要删除的材料")
            return

        material_id = int(self.table.item(row, 0).text())
        material_name = self.table.item(row, 2).text()

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除材料「{material_name}」吗？\n删除后无法恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            result = self.material_service.delete_material(material_id)
            if result.get("success"):
                QMessageBox.information(self, "成功", "材料已删除")
                self.load_materials()
            else:
                QMessageBox.warning(self, "删除失败", result.get("message", "删除失败"))


class MaterialEditDialog(QDialog):
    """材料编辑对话框"""

    def __init__(self, parent=None, material: dict = None):
        super().__init__(parent)
        self.material = material
        self.units = []
        self.suppliers = []
        self.init_ui()
        if material:
            self._load_material_data()

    def init_ui(self):
        self.setWindowTitle("编辑材料" if self.material else "新建材料")
        self.setFixedSize(500, 550)
        self.setStyleSheet("""
            QDialog {
                background-color: #f0f2f5;
            }
            QLabel {
                color: #333;
                font-size: 13px;
            }
            QLineEdit, QComboBox, QDoubleSpinBox {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #4a90e2;
            }
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton[cancel="true"] {
                background-color: #95a5a6;
            }
            QPushButton[cancel="true"]:hover {
                background-color: #7f8c8d;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 10)

        # 表单区
        form_frame = QWidget()
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        form_layout.setLabelWidth(90)

        # 加载单位和供应商
        self._load_units_and_suppliers()

        # 材料名称
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("请输入材料名称")
        form_layout.addRow("材料名称 *:", self.name_input)

        # 规格
        self.spec_input = QLineEdit()
        self.spec_input.setPlaceholderText("请输入规格型号")
        form_layout.addRow("规格:", self.spec_input)

        # 单位
        self.unit_combo = QComboBox()
        self._populate_unit_combo()
        form_layout.addRow("单位:", self.unit_combo)

        # 含税价
        self.tax_price_input = QDoubleSpinBox()
        self.tax_price_input.setRange(0, 99999999)
        self.tax_price_input.setDecimals(2)
        self.tax_price_input.setSuffix(" 元")
        self.tax_price_input.valueChanged.connect(self._on_tax_price_changed)
        form_layout.addRow("含税价 *:", self.tax_price_input)

        # 不含税价
        self.tax_exempt_input = QDoubleSpinBox()
        self.tax_exempt_input.setRange(0, 99999999)
        self.tax_exempt_input.setDecimals(2)
        self.tax_exempt_input.setSuffix(" 元")
        form_layout.addRow("不含税价:", self.tax_exempt_input)

        # 运费
        self.freight_input = QDoubleSpinBox()
        self.freight_input.setRange(0, 99999999)
        self.freight_input.setDecimals(2)
        self.freight_input.setSuffix(" 元")
        form_layout.addRow("运费:", self.freight_input)

        # 默认供应商
        self.supplier_combo = QComboBox()
        self._populate_supplier_combo()
        form_layout.addRow("默认供应商:", self.supplier_combo)

        # 库存下限
        self.min_input = QDoubleSpinBox()
        self.min_input.setRange(0, 99999999)
        self.min_input.setDecimals(2)
        form_layout.addRow("库存下限:", self.min_input)

        # 库存上限
        self.max_input = QDoubleSpinBox()
        self.max_input.setRange(0, 99999999)
        self.max_input.setDecimals(2)
        form_layout.addRow("库存上限:", self.max_input)

        # 备注
        self.remark_input = QTextEdit()
        self.remark_input.setPlaceholderText("请输入备注信息")
        self.remark_input.setMaximumHeight(80)
        form_layout.addRow("备注:", self.remark_input)

        form_frame.setLayout(form_layout)
        layout.addWidget(form_frame)

        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setProperty("cancel", True)
        cancel_btn.setFixedWidth(100)
        cancel_btn.clicked.connect(self.reject)

        self.ok_btn = QPushButton("确定")
        self.ok_btn.setFixedWidth(100)
        self.ok_btn.clicked.connect(self._on_ok)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self.ok_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _load_units_and_suppliers(self):
        """加载单位和供应商"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, unit_name FROM units ORDER BY unit_name")
        self.units = cursor.fetchall()

        cursor.execute("SELECT id, supplier_name FROM suppliers ORDER BY supplier_name")
        self.suppliers = cursor.fetchall()

        conn.close()

    def _populate_unit_combo(self):
        """填充单位下拉框"""
        self.unit_combo.clear()
        self.unit_combo.addItem("-- 请选择 --", None)
        for unit_id, unit_name in self.units:
            self.unit_combo.addItem(unit_name, unit_id)

    def _populate_supplier_combo(self):
        """填充供应商下拉框"""
        self.supplier_combo.clear()
        self.supplier_combo.addItem("-- 请选择 --", None)
        for supplier_id, supplier_name in self.suppliers:
            self.supplier_combo.addItem(supplier_name, supplier_id)

    def _on_tax_price_changed(self, value):
        """含税价变化时自动计算不含税价"""
        if value > 0:
            self.tax_exempt_input.setValue(round(value / 1.01, 2))

    def _load_material_data(self):
        """加载材料数据到表单"""
        self.name_input.setText(self.material.get("material_name", ""))
        self.spec_input.setText(self.material.get("specification", ""))
        self.tax_price_input.setValue(self.material.get("tax_price", 0) or 0)
        self.tax_exempt_input.setValue(self.material.get("tax_exempt_price", 0) or 0)
        self.freight_input.setValue(self.material.get("freight", 0) or 0)
        self.min_input.setValue(self.material.get("inventory_min", 0) or 0)
        self.max_input.setValue(self.material.get("inventory_max", 0) or 0)
        self.remark_input.setText(self.material.get("remark", ""))

        # 设置单位
        unit_id = self.material.get("unit_id")
        if unit_id:
            index = self.unit_combo.findData(unit_id)
            if index >= 0:
                self.unit_combo.setCurrentIndex(index)

        # 设置供应商
        supplier_id = self.material.get("default_supplier_id")
        if supplier_id:
            index = self.supplier_combo.findData(supplier_id)
            if index >= 0:
                self.supplier_combo.setCurrentIndex(index)

    def _on_ok(self):
        """确认保存"""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入材料名称")
            self.name_input.setFocus()
            return

        material = Material()
        if self.material:
            material.id = self.material.get("id")
        material.material_name = name
        material.specification = self.spec_input.text().strip()
        material.unit_id = self.unit_combo.currentData()
        material.tax_price = self.tax_price_input.value()
        material.tax_exempt_price = self.tax_exempt_input.value()
        material.freight = self.freight_input.value()
        material.default_supplier_id = self.supplier_combo.currentData()
        material.inventory_min = self.min_input.value()
        material.inventory_max = self.max_input.value()
        material.remark = self.remark_input.toPlainText().strip()

        service = MaterialService()
        if self.material:
            result = service.update_material(material)
        else:
            result = service.add_material(material)

        if result.get("success"):
            QMessageBox.information(self, "成功", "材料保存成功")
            self.accept()
        else:
            QMessageBox.warning(self, "失败", result.get("message", "保存失败"))
