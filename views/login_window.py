"""
登录窗口
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QCheckBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from services import AuthService


class LoginWindow(QWidget):
    """登录窗口"""

    login_success = pyqtSignal(dict)  # 登录成功信号，携带用户信息

    def __init__(self):
        super().__init__()
        self.auth_service = AuthService()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("零星材管理系统 - 登录")
        self.setFixedSize(400, 300)
        self.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
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
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QLineEdit {
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
            }
        """)

        # 主布局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(40, 40, 40, 40)

        # 标题
        title_label = QLabel("零星材管理系统")
        title_label.setFont(QFont("微软雅黑", 20, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # 副标题
        subtitle_label = QLabel("登录到系统")
        subtitle_label.setFont(QFont("微软雅黑", 10))
        subtitle_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(subtitle_label)

        main_layout.addSpacing(30)

        # 用户名
        username_layout = QHBoxLayout()
        username_label = QLabel("用户名:")
        username_label.setFixedWidth(60)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("请输入用户名")
        self.username_input.setFixedHeight(36)
        username_layout.addWidget(username_label)
        username_layout.addWidget(self.username_input)
        main_layout.addLayout(username_layout)

        main_layout.addSpacing(10)

        # 密码
        password_layout = QHBoxLayout()
        password_label = QLabel("密码:")
        password_label.setFixedWidth(60)
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("请输入密码")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setFixedHeight(36)
        self.password_input.returnPressed.connect(self.do_login)
        password_layout.addWidget(password_label)
        password_layout.addWidget(self.password_input)
        main_layout.addLayout(password_layout)

        # 记住登录
        self.remember_checkbox = QCheckBox("记住登录状态")
        main_layout.addWidget(self.remember_checkbox)

        main_layout.addSpacing(20)

        # 登录按钮
        self.login_btn = QPushButton("登 录")
        self.login_btn.setFixedHeight(40)
        self.login_btn.clicked.connect(self.do_login)
        main_layout.addWidget(self.login_btn)

        # 版本信息
        version_label = QLabel("v1.0.0")
        version_label.setFont(QFont("微软雅黑", 8))
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setStyleSheet("color: #999;")
        main_layout.addWidget(version_label)

        self.setLayout(main_layout)

    def do_login(self):
        """执行登录"""
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username:
            QMessageBox.warning(self, "提示", "请输入用户名")
            self.username_input.setFocus()
            return

        if not password:
            QMessageBox.warning(self, "提示", "请输入密码")
            self.password_input.setFocus()
            return

        result = self.auth_service.login(username, password)

        if result["success"]:
            self.login_success.emit(result["user"])
        else:
            QMessageBox.warning(self, "登录失败", result["message"])
            self.password_input.clear()
            self.password_input.setFocus()

    def center_on_screen(self):
        """窗口居中"""
        from PyQt5.QtWidgets import QDesktopWidget
        screen = QDesktopWidget().screenGeometry()
        window_geometry = self.geometry()
        x = (screen.width() - window_geometry.width()) // 2
        y = (screen.height() - window_geometry.height()) // 2
        self.move(x, y)
