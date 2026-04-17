"""
零星材管理系统 - 主入口
"""
import sys
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from database import init_database, insert_default_data, check_database_exists
from views import LoginWindow, MainWindow


def main():
    # 创建应用
    app = QApplication(sys.argv)

    # 设置应用字体
    font = QFont("微软雅黑", 10)
    app.setFont(font)

    # 初始化数据库
    try:
        init_database()
        if not check_database_exists():
            # 数据库为空，插入默认数据
            from database import get_connection
            conn = get_connection()
            insert_default_data(conn)
            conn.close()
    except Exception as e:
        QMessageBox.critical(None, "数据库错误", f"初始化数据库失败：\n{str(e)}")
        sys.exit(1)

    # 创建登录窗口
    login_window = LoginWindow()
    login_window.center_on_screen()

    def on_login_success(user: dict):
        """登录成功"""
        login_window.close()

        # 创建主窗口
        main_window = MainWindow(user)
        main_window.show()

        # 主窗口关闭后退出应用
        sys.exit(app.exec_())

    login_window.login_success.connect(on_login_success)
    login_window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
