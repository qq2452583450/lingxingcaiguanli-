# Windows 宝塔 Git 拉取部署

你的服务器信息：

```text
IP: 1.14.121.214
SSH 用户: Administrator
项目目录: C:\wwwroot\lxclgl
启动方式: Windows 服务自动启动
```

## 第一次准备服务器

在宝塔终端里确认有 Git 和 Python：

```powershell
git --version
python --version
```

如果没有 Git，需要先安装 Git for Windows。Python 也需要能在终端里直接运行 `python`。

## 第一次克隆项目

如果 `C:\wwwroot\lxclgl` 还不存在：

```powershell
cd C:\wwwroot
git clone https://github.com/qq2452583450/lingxingcaiguanli-.git lxclgl
cd C:\wwwroot\lxclgl
```

如果服务器现在已经有项目文件，但不是 Git 克隆出来的，先不要直接覆盖。建议先把现有目录改名备份：

```powershell
cd C:\wwwroot
Rename-Item lxclgl lxclgl-manual-backup
git clone https://github.com/qq2452583450/lingxingcaiguanli-.git lxclgl
```

然后把正式数据库复制回新目录：

```powershell
Copy-Item C:\wwwroot\lxclgl-manual-backup\零星材管理系统.db C:\wwwroot\lxclgl\零星材管理系统.db
```

## 配置服务器密钥

创建一个只存在服务器本地的配置文件：

```powershell
cd C:\wwwroot\lxclgl
Copy-Item deploy\server.env.ps1.example deploy\server.env.ps1
notepad deploy\server.env.ps1
```

把里面的值改成一串长一点的随机密钥：

```powershell
$env:SECRET_KEY = "你的随机密钥"
```

`deploy\server.env.ps1` 已被 `.gitignore` 排除，不会提交到 Git。

## 安装自动启动服务

推荐使用 NSSM 把项目注册为 Windows 服务。这样服务器重启后会自动启动，部署更新时也能自动重启，不需要手动输入 `python app.py`。

安装脚本会自动下载 NSSM 并放到：

```text
C:\wwwroot\lxclgl\tools\nssm.exe
```

在宝塔终端里执行一次：

```powershell
cd C:\wwwroot\lxclgl
powershell -ExecutionPolicy Bypass -File deploy\install-service.ps1
```

安装完成后会创建名为 `lxclgl` 的 Windows 服务，并设置为开机自启。

常用服务命令：

```powershell
Get-Service lxclgl
Restart-Service lxclgl
Stop-Service lxclgl
Start-Service lxclgl
```

## 每次更新服务器

本机改完代码后：

```powershell
git add .
git commit -m "说明本次更新内容"
git push
```

服务器宝塔终端执行：

```powershell
cd C:\wwwroot\lxclgl
powershell -ExecutionPolicy Bypass -File deploy\deploy.ps1
```

脚本会自动：

```text
备份服务器数据库到 backups\
git fetch / checkout / pull 最新代码
创建或复用 .venv
安装 requirements.txt
重启 lxclgl Windows 服务
检查 5000 端口是否监听
```

因为 `lxclgl` 已经是 Windows 服务，所以以后服务器重启也会自动启动，不需要再手动执行 `python app.py`。

## 如果端口不是 5000

```powershell
powershell -ExecutionPolicy Bypass -File deploy\deploy.ps1 -Port 5001
```

不过当前 `app.py` 写死启动在 5000，除非改代码，否则仍建议使用 5000。

## 注意

- 不要把服务器的 `零星材管理系统.db` 提交到 Git。
- 每次部署前脚本会备份数据库。
- `tools\nssm.exe` 是服务器本地文件，由安装脚本自动准备，不会提交到 Git。
- 如果 `git pull --ff-only` 失败，说明服务器项目目录里有人手工改过代码，需要先人工确认。
- 涉及角色权限更新时，用户需要退出重新登录。
