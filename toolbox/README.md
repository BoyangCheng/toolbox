# 荣信工具箱

Flask 应用，集成流程图编辑器 + 需求跟踪系统，支持多人登录协作。

## 功能

- **统一登录**：姓名 / 手机号 / 部门 / 密码 注册登录
- **流程图工具**：SVG 可视化编辑，多人在线（小绿点实时显示）、版本冲突检测、本地备份、复制粘贴
- **需求跟踪**：提交 / 评论 / 附件上传，自动记录提交人

## 目录结构

```
toolbox/
├── app.py              # Flask 主程序
├── requirements.txt    # Python 依赖
├── run.bat             # Windows 启动脚本（生产模式）
├── run.sh              # macOS/Linux 启动脚本
├── install.bat         # Windows 首次安装依赖
├── templates/          # Jinja2 模板
├── static/             # CSS/JS 资源
├── data/               # 流程图状态（flowchart_state.json）
├── data.db             # SQLite（用户、需求、评论）
├── uploads/            # 上传的图片
└── .secret_key         # session 密钥（自动生成）
```

---

## Windows 部署步骤

### 1. 准备机器
- 安装 **Python 3.10+**（https://www.python.org/downloads/windows/）
- **安装时务必勾选 `Add Python to PATH`**

### 2. 拷贝项目
把整个 `toolbox/` 文件夹拷到 Windows 机器任意位置，例如 `C:\toolbox\`。

> 注意：不要把 `.venv/` 文件夹从 macOS 拷过去，Windows 会重新生成。

### 3. 首次启动
双击 `run.bat`：
- 自动创建 `.venv/` 虚拟环境
- 自动 `pip install -r requirements.txt`（Flask、Werkzeug、waitress）
- 以生产模式（waitress）启动服务，监听 `0.0.0.0:5000`

首次启动需要几分钟（装依赖）。

### 4. 访问
- 本机：http://127.0.0.1:5000
- 同局域网其他电脑：http://<Windows-机器-IP>:5000
  - 查看 IP：CMD 运行 `ipconfig`，看 IPv4 地址

### 5. 开放防火墙（允许局域网访问）
以**管理员身份**打开 PowerShell，运行：
```powershell
New-NetFirewallRule -DisplayName "Toolbox 5000" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow
```

### 6. 后续启动
再次双击 `run.bat`，秒启（`.venv` 已存在跳过安装）。

### 7. 开机自启（可选）
- `Win + R` 输入 `shell:startup` 回车
- 把 `run.bat` 的**快捷方式**放到打开的启动文件夹里

---

## 升级代码

覆盖以下文件/目录即可，**千万不要动**下面第二组：

**可以覆盖**：
- `app.py`
- `templates/`
- `static/`
- `requirements.txt`（改动后删掉 `.venv/` 重新双击 `run.bat`）

**不要动**（这些是数据）：
- `data.db` — 用户和需求数据
- `data/flowchart_state.json` — 流程图
- `uploads/` — 上传图片
- `.secret_key` — 改了所有已登录用户会掉线

## 备份

定期复制这四项即可恢复：
```
data.db
data/
uploads/
.secret_key
```

---

## 切换开发 / 生产模式

`run.bat` 默认 `SERVER_MODE=prod`（waitress，多线程）。开发时可改成：
```bat
set SERVER_MODE=dev
```
这样会用 Flask 内置开发服务器（单线程，有访问日志）。

## 修改端口

```bat
set PORT=8080
```

## 停止服务

命令行窗口按 `Ctrl+C`，或直接关闭窗口。

## 常见问题

**Q: `run.bat` 会不会重置数据库？**
不会。`init_db()` 只建不存在的表，`CREATE TABLE IF NOT EXISTS`。

**Q: 多人同时编辑流程图会不会覆盖？**
有乐观锁：服务端校验 `_version`，冲突返回 409，前端弹「他人已修改」提示，并提供本地备份 + 强制覆盖选项。

**Q: 忘记密码？**
目前没有找回功能。临时方案：删 `data.db` 重建（会丢所有数据），或用 SQLite 工具手动改 `users.password_hash`。

**Q: Python 版本不够新？**
需要 3.10+。Windows 上 `python --version` 检查。
