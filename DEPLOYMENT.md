# Git 拉取部署说明

## 一次性准备

服务器需要安装：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

克隆代码：

```bash
cd /www
git clone https://github.com/qq2452583450/lingxingcaiguanli-.git lxclgl
cd /www/lxclgl
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p backups
```

把正式数据库放在项目目录：

```bash
/www/lxclgl/零星材管理系统.db
```

数据库文件不进 Git，更新代码时不会覆盖它。

## 配置 systemd 服务

复制模板：

```bash
sudo cp /www/lxclgl/deploy/lxclgl.service.example /etc/systemd/system/lxclgl.service
sudo nano /etc/systemd/system/lxclgl.service
```

至少修改：

```ini
WorkingDirectory=/www/lxclgl
Environment=SECRET_KEY=换成一串足够随机的密钥
ExecStart=/www/lxclgl/.venv/bin/python app.py
```

启用服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable lxclgl
sudo systemctl start lxclgl
sudo systemctl status lxclgl --no-pager
```

## 每次更新代码

本机：

```bash
git add .
git commit -m "说明本次更新内容"
git push
```

服务器：

```bash
cd /www/lxclgl
bash deploy/deploy.sh
```

脚本会做这些事：

```text
备份服务器数据库
拉取 Git 最新代码
安装 requirements.txt 依赖
重启 lxclgl 服务
显示服务状态
```

## 自定义部署目录或分支

如果服务器目录不是 `/www/lxclgl`，可以这样执行：

```bash
APP_DIR=/你的项目目录 SERVICE_NAME=你的服务名 BRANCH=main bash deploy/deploy.sh
```

## 注意

- 不要把服务器上的 `零星材管理系统.db` 提交到 Git。
- 更新前脚本会自动备份数据库到 `backups/`。
- 已登录用户可能缓存旧角色，涉及权限更新时需要重新登录。
- 如果 `git pull --ff-only` 失败，说明服务器上有本地改动，需要先人工确认，不能强行覆盖。
