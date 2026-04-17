"""
首页/工作台视图
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from database import get_connection
from helpers import get_today


class HomeView(QWidget):
    """首页/工作台视图"""

    navigate_to = pyqtSignal(str)  # 导航信号，携带模块名

    def __init__(self, current_user: dict):
        super().__init__()
        self.current_user = current_user
        self.init_ui()
        self.load_data()

    def init_ui(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #f0f2f5;
            }
            QFrame {
                background-color: white;
                border-radius: 8px;
            }
            QLabel {
                color: #333;
            }
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 顶部欢迎区
        welcome_frame = QFrame()
        welcome_layout = QHBoxLayout()
        welcome_label = QLabel(f"欢迎回来，{self.current_user.get('real_name', '用户')}")
        welcome_label.setFont(QFont("微软雅黑", 16, QFont.Bold))
        date_label = QLabel(get_today())
        date_label.setFont(QFont("微软雅黑", 12))
        date_label.setStyleSheet("color: #666;")
        welcome_layout.addWidget(welcome_label)
        welcome_layout.addStretch()
        welcome_layout.addWidget(date_label)
        welcome_frame.setLayout(welcome_layout)
        main_layout.addWidget(welcome_frame)

        main_layout.addSpacing(20)

        # 快捷入口
        shortcuts_label = QLabel("快捷入口")
        shortcuts_label.setFont(QFont("微软雅黑", 14, QFont.Bold))
        main_layout.addWidget(shortcuts_label)

        main_layout.addSpacing(10)

        # 快捷按钮区
        shortcuts_frame = QFrame()
        shortcuts_layout = QGridLayout()
        shortcuts_layout.setSpacing(15)

        # 快捷按钮定义
        buttons = [
            ("新建询价", "purchase_inquiry", ":/icons/inquiry.png"),
            ("新建入库", "stock_in", ":/icons/stock_in.png"),
            ("新建销售", "sales", ":/icons/sales.png"),
            ("对账管理", "reconciliation", ":/icons/reconciliation.png"),
            ("材料管理", "material", ":/icons/material.png"),
            ("库存查询", "inventory", ":/icons/inventory.png"),
        ]

        for i, (text, module, icon) in enumerate(buttons):
            btn = QPushButton(text)
            btn.setFixedSize(120, 80)
            btn.setFont(QFont("微软雅黑", 12))
            btn.clicked.connect(lambda checked, m=module: self.navigate_to.emit(m))
            shortcuts_layout.addWidget(btn, i // 3, i % 3)

        shortcuts_frame.setLayout(shortcuts_layout)
        main_layout.addWidget(shortcuts_frame)

        main_layout.addSpacing(20)

        # 待办事项区
        todo_label = QLabel("待办事项")
        todo_label.setFont(QFont("微软雅黑", 14, QFont.Bold))
        main_layout.addWidget(todo_label)

        main_layout.addSpacing(10)

        # 待办卡片区
        todo_frame = QFrame()
        todo_layout = QHBoxLayout()
        todo_layout.setSpacing(15)

        # 待审批数量
        self.pending_approval_card = self._create_card("待审批", "0", "#e74c3c")
        todo_layout.addWidget(self.pending_approval_card)

        # 库存预警数量
        self.inventory_warning_card = self._create_card("库存预警", "0", "#f39c12")
        todo_layout.addWidget(self.inventory_warning_card)

        # 今日入库数量
        self.today_in_card = self._create_card("今日入库", "0", "#27ae60")
        todo_layout.addWidget(self.today_in_card)

        # 今日销售数量
        self.today_out_card = self._create_card("今日销售", "0", "#3498db")
        todo_layout.addWidget(self.today_out_card)

        todo_frame.setLayout(todo_layout)
        main_layout.addWidget(todo_frame)

        main_layout.addStretch()

        self.setLayout(main_layout)

    def _create_card(self, title: str, value: str, color: str) -> QFrame:
        """创建统计卡片"""
        card = QFrame()
        card.setFixedSize(150, 100)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: white;
                border-left: 4px solid {color};
                border-radius: 4px;
            }}
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 10)

        title_label = QLabel(title)
        title_label.setFont(QFont("微软雅黑", 10))
        title_label.setStyleSheet("color: #666;")
        layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setFont(QFont("微软雅黑", 24, QFont.Bold))
        value_label.setStyleSheet(f"color: {color};")
        layout.addWidget(value_label)

        card.setLayout(layout)
        return card

    def load_data(self):
        """加载数据"""
        conn = get_connection()
        cursor = conn.cursor()
        today = get_today()

        # 待审批数量
        cursor.execute("""
            SELECT COUNT(*) FROM purchase_inquiries
            WHERE approval_status = '待审批' OR approval_status = '材料员已审'
        """)
        pending = cursor.fetchone()[0]
        self._update_card_value(self.pending_approval_card, str(pending))

        # 库存预警数量（低于下限）
        cursor.execute("""
            SELECT COUNT(*) FROM materials m
            LEFT JOIN inventory i ON m.id = i.material_id
            WHERE m.inventory_min > 0 AND (i.quantity IS NULL OR i.quantity < m.inventory_min)
        """)
        warning = cursor.fetchone()[0]
        self._update_card_value(self.inventory_warning_card, str(warning))

        # 今日入库
        cursor.execute("""
            SELECT COUNT(*) FROM stock_in_orders WHERE DATE(in_time) = ?
        """, (today,))
        today_in = cursor.fetchone()[0]
        self._update_card_value(self.today_in_card, str(today_in))

        # 今日销售
        cursor.execute("""
            SELECT COUNT(*) FROM sales_orders WHERE DATE(create_time) = ?
        """, (today,))
        today_out = cursor.fetchone()[0]
        self._update_card_value(self.today_out_card, str(today_out))

        conn.close()

    def _update_card_value(self, card: QFrame, value: str):
        """更新卡片值"""
        layout = card.layout()
        if layout and layout.count() >= 2:
            value_label = layout.itemAt(1).widget()
            if value_label:
                value_label.setText(value)
