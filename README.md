# 荣信工具箱

公司内部工具集合，统一登录、流程图协同编辑、需求收集与跟踪。

## 仓库结构

```
.
├── toolbox/                 ← 主应用（统一入口、登录、流程图、需求跟踪）
├── requestFromToBoyang/     ← 早期独立的需求收集 Flask 应用（已并入 toolbox/）
└── custom-flow-chart/       ← 早期 Node.js 版流程图原型（已并入 toolbox/）
```

> 推荐统一使用 [`toolbox/`](toolbox/)，另外两个保留作为参考。下面所有部署说明均针对 `toolbox/`。

## 主要功能

- **统一登录**：姓名 / 手机号 / 部门 / 密码
- **流程图编辑器**：SVG 可视化，节点/连线/分组、撤回重做、跨平台快捷键
- **多人协作**：实时在线提示、乐观锁冲突检测、本地 localStorage 兜底
- **服务端版本归档**：闲置 10 分钟 / 连续编辑 20 分钟 / 离开页面自动归档；支持版本浏览与一键恢复
- **需求跟踪**：提交 / 评论 / 点赞 / 状态 / 图片上传

---

# 部署方式

按使用场景分两类：

| 场景 | 用途 | 推荐方式 |
|---|---|---|
| **局域网部署** | 内部团队 5～50 人，仅需在公司 WiFi/网线 内访问 | Mac launchd / Windows `run.bat` |
| **生产部署** | 公网访问、HTTPS、稳定性要求高 | Linux + systemd + nginx + Let's Encrypt |

---

## 一、局域网部署

适合：公司内部一台机器永久跑服务，同事通过 LAN IP 访问。无需公网、无需域名。

### A. macOS（当前已部署）

已通过 `launchd` 配成开机自启 + 崩溃自动重启，使用 waitress（生产 WSGI）跑在 5000 端口。

#### 1. LaunchAgent 文件

位置：`~/Library/LaunchAgents/com.rongxin.toolbox.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.rongxin.toolbox</string>

  <key>ProgramArguments</key>
  <array>
    <string>/Users/vibrant-wellness/toolbox/toolbox/.venv/bin/python</string>
    <string>/Users/vibrant-wellness/toolbox/toolbox/app.py</string>
  </array>

  <key>WorkingDirectory</key>
  <string>/Users/vibrant-wellness/toolbox/toolbox</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>SERVER_MODE</key>
    <string>prod</string>
    <key>PORT</key>
    <string>5000</string>
  </dict>

  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>

  <key>StandardOutPath</key>
  <string>/Users/vibrant-wellness/toolbox/toolbox/data/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/vibrant-wellness/toolbox/toolbox/data/launchd.err.log</string>
</dict>
</plist>
```

#### 2. 首次部署命令

```bash
# 1. 准备虚拟环境（首次或依赖变更后）
cd /Users/vibrant-wellness/toolbox/toolbox
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. 验证 plist 格式
plutil -lint ~/Library/LaunchAgents/com.rongxin.toolbox.plist

# 3. 加载并启动
launchctl load -w ~/Library/LaunchAgents/com.rongxin.toolbox.plist

# 4. 确认运行
launchctl list | grep rongxin
lsof -iTCP:5000 -sTCP:LISTEN
curl -sI http://127.0.0.1:5000/login    # 应返回 HTTP/1.1 200 + Server: waitress
```

#### 3. 日常运维

```bash
# 状态
launchctl list | grep rongxin

# 重启（更新代码后）
launchctl unload ~/Library/LaunchAgents/com.rongxin.toolbox.plist
launchctl load   ~/Library/LaunchAgents/com.rongxin.toolbox.plist

# 完全停止（不再自启）
launchctl unload -w ~/Library/LaunchAgents/com.rongxin.toolbox.plist

# 看日志
tail -f /Users/vibrant-wellness/toolbox/toolbox/data/launchd.err.log
tail -f /Users/vibrant-wellness/toolbox/toolbox/data/launchd.out.log
```

#### 4. 注意事项

- **防火墙**：第一次有同事访问时，macOS 会弹"是否允许 Python 接受网络连接" → 点**允许**。
- **休眠**：Mac 进睡眠服务暂停。`系统设置 → 电池/电源 → 永不休眠`，或仅在接电源时不休眠。
- **IP 漂移**：建议在路由器后台为这台 Mac 绑定 MAC ↔ 静态 IP，否则同事访问的 URL 可能突然失效。
- **更新代码后**：`git pull` → 重启服务命令即可生效。

---

### B. Windows 局域网部署

#### 1. 准备
- 安装 Python 3.10+（官网下载，**勾选 Add Python to PATH**）
- 把 `toolbox/` 目录拷到机器上（不要带 `.venv/`，会重新生成）

#### 2. 首次启动

双击 `toolbox/run.bat`，自动：
- 创建 `.venv/`
- 安装依赖（Flask, Werkzeug, waitress）
- 以 `SERVER_MODE=prod` 启动 waitress，监听 `0.0.0.0:5000`

#### 3. 开放防火墙

管理员 PowerShell：

```powershell
New-NetFirewallRule -DisplayName "Toolbox 5000" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow
```

#### 4. 开机自启

- `Win+R` → 输入 `shell:startup` 回车
- 把 `run.bat` 的**快捷方式**拖进打开的文件夹

#### 5. 装成 Windows 服务（推荐，关电源/锁屏/无人登录都不掉）

用 [NSSM](https://nssm.cc/download)：

```cmd
:: 解压 NSSM 后
nssm install Toolbox C:\toolbox\.venv\Scripts\python.exe C:\toolbox\app.py
nssm set Toolbox AppDirectory C:\toolbox
nssm set Toolbox AppEnvironmentExtra SERVER_MODE=prod PORT=5000
nssm set Toolbox AppStdout C:\toolbox\data\service.out.log
nssm set Toolbox AppStderr C:\toolbox\data\service.err.log
nssm set Toolbox Start SERVICE_AUTO_START
nssm start Toolbox

:: 查看状态
nssm status Toolbox

:: 停止 / 重启
nssm stop Toolbox
nssm restart Toolbox
```

#### 6. 访问

```
http://<windows-机器-IP>:5000
```

`ipconfig` 查看 IPv4 地址。

---

## 二、生产部署（公网 / HTTPS）

适合：要给跨地区员工访问，或需要 HTTPS、备份策略、监控告警的场景。下面以 Ubuntu 22.04 + nginx 为例。

### 1. 系统准备

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv nginx git certbot python3-certbot-nginx
```

### 2. 拉代码 + 安装依赖

```bash
sudo useradd -m -s /bin/bash toolbox
sudo -u toolbox bash <<'EOF'
cd ~
git clone https://github.com/BoyangCheng/toolbox.git
cd toolbox/toolbox
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
EOF
```

### 3. systemd 单元

`/etc/systemd/system/toolbox.service`：

```ini
[Unit]
Description=Rongxin Toolbox
After=network.target

[Service]
Type=simple
User=toolbox
Group=toolbox
WorkingDirectory=/home/toolbox/toolbox/toolbox
Environment=SERVER_MODE=prod
Environment=PORT=5000
ExecStart=/home/toolbox/toolbox/toolbox/.venv/bin/python /home/toolbox/toolbox/toolbox/app.py
Restart=always
RestartSec=5
StandardOutput=append:/var/log/toolbox.out.log
StandardError=append:/var/log/toolbox.err.log

[Install]
WantedBy=multi-user.target
```

启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now toolbox
sudo systemctl status toolbox
```

### 4. nginx 反代 + HTTPS

`/etc/nginx/sites-available/toolbox`：

```nginx
server {
    listen 80;
    server_name toolbox.your-domain.com;

    client_max_body_size 20M;     # 允许 16MB 图片上传

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

启用 + 申请 HTTPS：

```bash
sudo ln -s /etc/nginx/sites-available/toolbox /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d toolbox.your-domain.com   # 自动配 HTTPS + 续签
```

### 5. 运维

```bash
# 服务状态
sudo systemctl status toolbox

# 重启（部署新版本）
cd ~/toolbox && git pull
sudo systemctl restart toolbox

# 看日志
sudo journalctl -u toolbox -f
sudo tail -f /var/log/toolbox.err.log

# nginx 日志
sudo tail -f /var/log/nginx/access.log
```

### 6. 自动备份（每日凌晨 2 点）

`crontab -e`（toolbox 用户）：

```
0 2 * * * tar -czf /home/toolbox/backups/toolbox-$(date +\%Y\%m\%d).tar.gz -C /home/toolbox/toolbox/toolbox data data.db uploads .secret_key && find /home/toolbox/backups -mtime +30 -delete
```

---

## 三、Docker 部署（可选）

最小 `Dockerfile`（放在 `toolbox/` 内）：

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV SERVER_MODE=prod PORT=5000
EXPOSE 5000
CMD ["python", "app.py"]
```

`docker-compose.yml`：

```yaml
services:
  toolbox:
    build: ./toolbox
    ports:
      - "5000:5000"
    volumes:
      - ./toolbox/data:/app/data
      - ./toolbox/uploads:/app/uploads
      - ./toolbox/data.db:/app/data.db
    restart: unless-stopped
```

```bash
docker compose up -d
docker compose logs -f
```

---

# 配置项（环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `SERVER_MODE` | `dev` | `prod` 用 waitress（多线程，无访问日志），`dev` 用 Flask 内置（单线程，有访问日志） |
| `PORT` | `5000` | 监听端口 |

---

# 升级 / 备份 / 故障排查

## 部署新版本

```bash
git pull
# 然后根据部署方式重启服务（见各部署章节"运维"小节）
```

> 如果 `requirements.txt` 有改动：
> - macOS/Linux: `cd toolbox && .venv/bin/pip install -r requirements.txt`
> - Windows: 删 `.venv\` 文件夹后重跑 `run.bat`

## 数据备份

定期复制 `toolbox/` 内这四项即可完整恢复：

| 路径 | 说明 |
|---|---|
| `data.db` | 用户、需求、评论 |
| `data/flowchart_state.json` | 流程图当前状态 |
| `data/flowchart_versions/` | 流程图历史版本快照 |
| `uploads/` | 用户上传的图片 |
| `.secret_key` | session 签名密钥（覆盖会让所有人掉线） |

## 常见问题

**Q: 多人同时编辑流程图会不会互相覆盖？**
A: 服务端有乐观锁 (`_version`)，冲突返回 409，前端弹"他人已修改"对话框，提供"刷新"/"暂不刷新"/"强制覆盖"三个选项，并保留本地 localStorage 兜底。

**Q: 流程图改坏了怎么回滚？**
A: 工具栏点 `📜 版本` → 选历史版本 → 点 `恢复`。系统会先把当前状态自动归档为一个新版本（标签 `pre-restore-from-vN`），再恢复目标版本，所以恢复操作本身可逆。

**Q: 忘记密码？**
A: 当前没有自助找回。临时方案：用 SQLite 客户端打开 `data.db`，在 `users` 表中改 `password_hash`（用 `werkzeug.security.generate_password_hash` 生成）。

**Q: Mac 部署后同事访问失败？**
A: 检查清单：
1. `lsof -iTCP:5000 -sTCP:LISTEN` 看服务有没有起来
2. macOS 防火墙弹窗有没有点"允许"（系统设置 → 网络 → 防火墙 → 应用列表里检查 Python）
3. Mac 是不是睡眠了
4. IP 是否变了 — `ipconfig getifaddr en0` 看当前 IP

**Q: 怎么彻底重置数据库？**
A: 停服务 → 删 `data.db`、`data/`、`uploads/`、`.secret_key` → 重启服务（`init_db()` 会自动建表）。

---

# 开发

```bash
cd toolbox
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py    # 默认 dev 模式，有访问日志
```

代码风格：4 空格缩进、`snake_case` 函数名、所有 SQL 用占位符（防注入）。前端无构建步骤，纯 Jinja + 原生 JS。
