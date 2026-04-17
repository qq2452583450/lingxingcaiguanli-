"""
主窗口
"""
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QStackedWidget, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QIcon

from views.home_view import HomeView
from views.material_view import MaterialListView
from views.purchase_inquiry_view import PurchaseInquiryListView


class MainWindow(QMainWindow):
    """主窗口"""

    logout_signal = pyqtSignal()  # 退出登录信号

    def __init__(self, current_user: dict):
        super().__init__()
        self.current_user = current_user
        self.current_view = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("零星材管理系统")
        self.setMinimumSize(1200, 800)

        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局（左侧菜单 + 右侧内容）
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 左侧导航栏
        nav_widget = self._create_navigation()
        main_layout.addWidget(nav_widget)

        # 右侧内容区
        self.content_stack = QStackedWidget()
        main_layout.addWidget(self.content_stack, 1)

        central_widget.setLayout(main_layout)

        # 默认显示首页
        self.show_view("home")

    def _create_navigation(self) -> QWidget:
        """创建左侧导航栏"""
        nav_widget = QWidget()
        nav_widget.setFixedWidth(220)
        nav_widget.setStyleSheet("""
            QWidget {
                background-color: #2c3e50;
            }
            QPushButton {
                background-color: transparent;
                color: #bdc3c7;
                border: none;
                text-align: left;
                padding: 12px 20px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #34495e;
                color: white;
            }
            QPushButton.active {
                background-color: #4a90e2;
                color: white;
            }
            QLabel {
                color: white;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部标题
        title_frame = QFrame()
        title_frame.setFixedHeight(80)
        title_layout = QVBoxLayout()
        title_layout.setContentsMargins(15, 20, 15, 10)
        title_label = QLabel("零星材管理")
        title_label.setFont(QFont("微软雅黑", 16, QFont.Bold))
        title_layout.addWidget(title_label)
        subtitle_label = QLabel("v1.0.0")
        subtitle_label.setFont(QFont("微软雅黑", 9))
        subtitle_label.setStyleSheet("color: #7f8c8d;")
        title_layout.addWidget(subtitle_label)
        title_frame.setLayout(title_layout)
        layout.addWidget(title_frame)

        # 导航分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #34495e;")
        line.setFixedHeight(1)
        layout.addWidget(line)

        # 导航菜单
        nav_items = [
            ("home", "首页", ":/icons/home.png"),
            ("material", "材料信息管理", ":/icons/material.png"),
            ("purchase_inquiry", "采购管理-询比价", ":/icons/inquiry.png"),
            ("purchase_order", "采购管理-集采", ":/icons/order.png"),
            ("stock_in", "仓库管理-入库", ":/icons/stock_in.png"),
            ("stock_out", "仓库管理-出库", ":/icons/stock_out.png"),
            ("inventory", "仓库管理-库存", ":/icons/inventory.png"),
            ("reconciliation", "对账管理", ":/icons/reconciliation.png"),
            ("sales", "销售管理", ":/icons/sales.png"),
            ("customer", "客户管理", ":/icons/customer.png"),
            ("supplier", "供应商管理", ":/icons/supplier.png"),
            ("report", "报表统计", ":/icons/report.png"),
            ("system", "系统设置", ":/icons/system.png"),
        ]

        self.nav_buttons = {}
        for module, text, icon in nav_items:
            btn = QPushButton(f"  {text}")
            btn.setFont(QFont("微软雅黑", 12))
            btn.setFixedHeight(45)
            btn.clicked.connect(lambda checked, m=module: self.show_view(m))
            self.nav_buttons[module] = btn
            layout.addWidget(btn)

        layout.addStretch()

        # 底部用户信息
        user_frame = QFrame()
        user_frame.setFixedHeight(60)
        user_frame.setStyleSheet("background-color: #34495e;")
        user_layout = QVBoxLayout()
        user_layout.setContentsMargins(15, 8, 15, 8)
        user_name = QLabel(self.current_user.get("real_name", "用户"))
        user_name.setFont(QFont("微软雅黑", 11))
        user_name.setStyleSheet("color: white;")
        user_layout.addWidget(user_name)
        user_role = QLabel(self.current_user.get("role_name", ""))
        user_role.setFont(QFont("微软雅黑", 9))
        user_role.setStyleSheet("color: #95a5a6;")
        user_layout.addWidget(user_role)
        user_frame.setLayout(user_layout)
        layout.addWidget(user_frame)

        nav_widget.setLayout(layout)
        return nav_widget

    def show_view(self, module: str):
        """切换视图"""
        # 更新导航按钮状态
        for key, btn in self.nav_buttons.items():
            if key == module:
                btn.setProperty("active", True)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            else:
                btn.setProperty("active", False)
                btn.style().unpolish(btn)
                btn.style().polish(btn)

        # 根据模块切换内容
        if module == "home":
            view = HomeView(self.current_user)
            view.navigate_to.connect(self.show_view)
            self._switch_content(view, "home")
        elif module == "material":
            view = MaterialListView(self.current_user)
            self._switch_content(view, "material")
        elif module == "purchase_inquiry":
            view = PurchaseInquiryListView(self.current_user)
            self._switch_content(view, "purchase_inquiry")
        elif module == "purchase_order":
            self._show_placeholder("集中采购管理", module)
        elif module == "stock_in":
            self._show_placeholder("入库管理", module)
        elif module == "stock_out":
            self._show_placeholder("出库管理", module)
        elif module == "inventory":
            self._show_placeholder("库存管理", module)
        elif module == "reconciliation":
            self._show_placeholder("对账管理", module)
        elif module == "sales":
            self._show_placeholder("销售管理", module)
        elif module == "customer":
            self._show_placeholder("客户管理", module)
        elif module == "supplier":
            self._show_placeholder("供应商管理", module)
        elif module == "report":
            self._show_placeholder("报表统计", module)
        elif module == "system":
            self._show_placeholder("系统设置", module)

    def _switch_content(self, view: QWidget, key: str):
        """切换内容"""
        # 如果已存在则移除
        for i in range(self.content_stack.count()):
            widget = self.content_stack.widget(i)
            if widget and widget.objectName() == key:
                self.content_stack.removeWidget(widget)
                widget.deleteLater()
                break

        view.setObjectName(key)
        self.content_stack.addWidget(view)
        self.content_stack.setCurrentWidget(view)
        self.current_view = view

    def _show_placeholder(self, title: str, module: str):
        """显示占位视图"""
        from PyQt5.QtWidgets import QScrollArea, QSizePolicy
        placeholder = QWidget()
        placeholder.setObjectName(module)
        layout = QVBoxLayout()

        # 标题
        title_label = QLabel(title)
        title_label.setFont(QFont("微软雅黑", 20, QFont.Bold))
        title_label.setStyleSheet("color: #2c3e50; padding: 20px;")
        layout.addWidget(title_label)

        # 提示
        hint_label = QLabel("此模块正在开发中...")
        hint_label.setFont(QFont("微软雅黑", 14))
        hint_label.setStyleSheet("color: #95a5a6; padding: 20px;")
        hint_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint_label)

        layout.addStretch()
        placeholder.setLayout(layout)

        self._switch_content(placeholder, module)

    def closeEvent(self, event):
        """关闭窗口"""
        reply = QMessageBox.question(
            self, "确认退出",
            "确定要退出系统吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()
