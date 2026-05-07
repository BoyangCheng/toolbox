# Toolbox + WaterMirror 完整部署手册

同一台阿里云 ECS 上跑 toolbox 和 watermirror 两个服务，nginx 反代，HTTPS。本文是从零到上线的完整流程合订本。

---

## 1. 系统总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                          阿里云 ECS                                 │
│                                                                     │
│  ┌────────────────────────────────────────────────────────┐        │
│  │  nginx :80 / :443  (HTTPS via Let's Encrypt)            │        │
│  └─────────┬──────────────────────────┬──────────────────┘        │
│            │                          │                             │
│   toolbox.droplets.com.cn   watermirror.droplets.com.cn            │
│            │                          │                             │
│            ▼                          ▼                             │
│  ┌──────────────────┐      ┌─────────────────────┐                 │
│  │ rongxin-toolbox  │      │ watermirror         │                 │
│  │ 127.0.0.1:5000   │      │ 127.0.0.1:3000      │                 │
│  │ (Flask+waitress) │      │ (Next.js)           │                 │
│  │                  │      │                     │                 │
│  │ 数据：           │      │ 数据：              │                 │
│  │ /opt/toolbox/    │      │ 阿里云 PolarDB      │                 │
│  │   docker-data/   │      │ 阿里云 OSS          │                 │
│  └──────────────────┘      └─────────────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
                              ▲
                              │ ACR pull
                              │
              registry.cn-hangzhou.aliyuncs.com (个人独立实例)
                              ▲
                              │ ./push.sh (Mac 本地 build)
                              │
                          开发机 Mac
```

| 关键参数 | 值 |
|---|---|
| ECS 公网 IP | `116.62.53.22` |
| toolbox 域名 | `toolbox.droplets.com.cn` |
| watermirror 域名 | `watermirror.droplets.com.cn` |
| ACR 实例 endpoint | `crpi-ynsvk82qr21rkkzo.cn-hangzhou.personal.cr.aliyuncs.com` |
| ACR 命名空间 | `watermirror`（仅 watermirror 用） |
| toolbox 部署目录 | `/opt/toolbox` |
| watermirror 部署目录 | `/opt/waterMirror` |

| 服务 | 容器端口 | 主机端口（127.0.0.1 only） | 监听类型 |
|---|---|---|---|
| toolbox | 5000 | `127.0.0.1:5000` | Flask + waitress |
| watermirror | 3000 | `127.0.0.1:3000` | Next.js standalone |

> **重要原则**：两个服务的端口都只绑 `127.0.0.1`，不暴露公网。所有对外流量通过 nginx 进入。

---

## 2. 一次性环境准备（首次部署做一遍）

### 2.1 阿里云控制台

#### A. 域名解析（云解析 DNS）

`droplets.com.cn` → 解析设置 → 添加 A 记录：

| 主机记录 | 类型 | 记录值 | TTL |
|---|---|---|---|
| `toolbox` | A | `116.62.53.22` | 600 |
| `watermirror` | A | `116.62.53.22` | 600 |

> `.cn` 域名需主域名已 ICP 备案，子域名继承。

#### B. ECS 安全组

入方向必须开放：

| 协议 | 端口 | 授权对象 | 用途 |
|---|---|---|---|
| TCP | 22 | 你的 IP 或 0.0.0.0/0 | SSH |
| TCP | 80 | 0.0.0.0/0 | HTTP（certbot 验证 + 重定向） |
| TCP | 443 | 0.0.0.0/0 | HTTPS |

**禁止**对外开放 5000、3000（nginx 已经反代，开了反而是攻击面）。

#### C. PolarDB 白名单（仅 watermirror 需要）

PolarDB 控制台 → `watermirror-01` 集群 → 白名单设置 → 添加 ECS 的 **VPC 内网 IP**（`hostname -I` 看）。

#### D. ACR 准备（仅 watermirror 需要）

1. 容器镜像服务 ACR → 个人实例 → 启用
2. 命名空间 → 创建 `watermirror`
3. 访问凭证 → **设置 Registry 登录密码**（不是 Aliyun 账号密码！）
4. 镜像仓库 → 创建 `watermirror`（首次 push 也会自动创建）

#### E. Authing（仅 watermirror 需要）

应用配置 → 加回调白名单：
```
https://watermirror.droplets.com.cn/api/auth/callback
```

#### F. OSS（仅 watermirror 需要）

bucket `water-mirror-bucket` → 跨域设置 → 加规则：
```
来源:    https://watermirror.droplets.com.cn
方法:    GET POST PUT DELETE HEAD
Headers: *
```

### 2.2 ECS 系统初始化

```bash
ssh root@116.62.53.22

apt update && apt upgrade -y
apt install -y git curl ufw nano
timedatectl set-timezone Asia/Shanghai

# 创建非 root 用户（更安全）
useradd -m -s /bin/bash deploy
usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
```

后续操作用 `ssh deploy@116.62.53.22`。

### 2.3 装 Docker + 配多镜像加速器

> ⚠️ 不要只用阿里云免费 mirror（`xxx.mirror.aliyuncs.com`）—— 它从 2024 年起对常见镜像（如 `python:3.12-slim`）经常返回 404。

```bash
ssh deploy@116.62.53.22

# clone toolbox 仓库（包含 deploy 脚本）
sudo mkdir -p /opt && sudo chown deploy:deploy /opt
cd /opt
git clone https://github.com/BoyangCheng/toolbox.git

# 一键装 Docker + 多 mirror fallback
cd /opt/toolbox
sudo ./deploy/setup-docker.sh --install

# 让 deploy 用户免 sudo 用 docker
sudo usermod -aG docker deploy

# 退出重连让 docker 组生效
exit
ssh deploy@116.62.53.22
```

验证：

```bash
docker info | grep -A 5 "Registry Mirrors"
docker pull hello-world  # 拉得动 = mirror 通
```

---

## 3. 部署 toolbox（在 ECS 上 build）

> toolbox 镜像很轻量（~150MB），直接在 ECS build 也只需 1-2 分钟，不用走 ACR。

```bash
ssh deploy@116.62.53.22
cd /opt/toolbox

# 拉最新代码（首次部署可跳过，clone 已经是最新了）
git pull

# 启动（首次会 build 镜像 + 创建容器）
docker compose up -d --build

# 看日志确认正常
docker compose logs -f --tail=30
# 看到 "Serving on http://0.0.0.0:5000" 即 OK，Ctrl+C 退出

# 验证后端可达
curl -sI http://127.0.0.1:5000/login
# 应返回 HTTP/1.1 200 OK · Server: waitress
```

### toolbox 数据持久化

所有数据写入 `/opt/toolbox/docker-data/`，通过 entrypoint symlink 桥接到容器：

```
/opt/toolbox/docker-data/
├── data.db                          # 用户/需求/评论 SQLite
├── secret_key                       # session 签名密钥
├── data/
│   ├── flowchart_state.json
│   └── flowchart_versions/          # 流程图历史版本（4天内全留，超出每日留最晚）
└── uploads/                         # 上传图片 + 节点附件
```

**容器升级 / 重建不会丢数据**。备份只需打包这一个目录。

### 更新 toolbox

```bash
ssh deploy@116.62.53.22
cd /opt/toolbox
git pull
docker compose up -d --build
docker compose logs -f --tail=20
```

---

## 4. 部署 watermirror（Mac build → ACR → ECS pull）

> watermirror 是 Next.js 大项目，build 时单进程峰值 2-4GB 内存。**绝不要在 ECS 上 build**（小机型会被 OOM 锁死整机）。流程是：本地 Mac build → push 到 ACR → ECS 只 pull。

### 4.1 一次性：本地 Mac 准备

```bash
# Mac 上
cd /Users/vibrant-wellness/waterMirror

# 1. 装 Docker Desktop（macOS 版本，拖进 Applications）
# 2. 启动 Docker Desktop（菜单栏看到鲸鱼图标）
docker info  # 能跑就 OK

# 3. 登录 ACR
docker login --username=bchg4 \
    crpi-ynsvk82qr21rkkzo.cn-hangzhou.personal.cr.aliyuncs.com
# 密码 = ACR 控制台 → 访问凭证 → 设的 Registry 登录密码（不是阿里云账号密码）

# 4. 检查 .env.production 有正确的生产 URL（用于 build args）
grep '^NEXT_PUBLIC_' .env.production
# 应该看到:
# NEXT_PUBLIC_LIVE_URL=https://watermirror.droplets.com.cn
# NEXT_PUBLIC_SITE_URL=https://watermirror.droplets.com.cn
# NEXT_PUBLIC_AUTHING_APP_HOST=https://droplets.authing.cn
```

### 4.2 一次性：ECS 准备

```bash
ssh deploy@116.62.53.22

# 1. clone watermirror 仓库到 /opt
cd /opt
git clone <watermirror-repo-url> waterMirror
cd waterMirror

# 2. 准备生产 .env
cp .env.production .env
# 检查所有字段都有值（特别是 DATABASE_URL, AUTHING_*, OSS_*）
grep -c '=$' .env  # 输出 0 = 没有空值

# 3. ECS 上也登录 ACR
docker login --username=bchg4 \
    crpi-ynsvk82qr21rkkzo.cn-hangzhou.personal.cr.aliyuncs.com
```

### 4.3 日常 build & push（每次代码改了之后）

#### Mac 上 push

```bash
cd /Users/vibrant-wellness/waterMirror

# 1. 提交代码
git add .
git commit -m "..."
git push

# 2. build linux/amd64 镜像并推送到 ACR
./push.sh watermirror

# 整个流程约 6-15 分钟：
# - yarn install (3-5 min)
# - next build (3-8 min)
# - docker push 到 ACR (2-5 min)
```

`push.sh` 自动从 `.env.production` 读取 `NEXT_PUBLIC_*` 注入到 build args，所以生产 URL 会被正确烧进客户端 bundle。

成功后输出：

```
🎉 推送完成！
镜像地址: crpi-ynsvk82qr21rkkzo.cn-hangzhou.personal.cr.aliyuncs.com/watermirror/watermirror:latest
commit tag: ...:<git-hash>
```

#### ECS 上 pull + 启动

```bash
ssh deploy@116.62.53.22
cd /opt/waterMirror

# 一键更新（推荐）
./update.sh

# 或手动
git pull
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f --tail=30
```

`update.sh` 做的事：
1. `git pull` 拉最新代码
2. 检查 ACR 登录状态
3. `docker pull` 拉最新 `:latest` 镜像
4. `docker compose up -d` 滚动更新
5. 健康检查（最多重试 10 次 × 3 秒）
6. `docker image prune` 清旧镜像
7. 显示 `docker compose ps` 状态

### 4.4 watermirror 数据持久化

**没有本地持久化目录** —— 所有数据都在云端：

| 数据 | 位置 |
|---|---|
| 业务数据（用户/面试/对话） | 阿里云 PolarDB |
| 上传文件（简历/图片） | 阿里云 OSS bucket `water-mirror-bucket` |
| 用户账号 | Authing 云端 |
| 配置 | `/opt/waterMirror/.env` |

容器随便重建、删除都不会丢数据。

### 4.5 仅改 `.env` 时的更新（不需要重 build 镜像）

server-only env vars（`AUTHING_APP_ID` 等）改了：

```bash
ssh deploy@116.62.53.22
cd /opt/waterMirror
nano .env  # 改对应字段，保存

# ⚠️ 必须 down + up，不能用 restart
# restart 不会重新读 .env！
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d

# 验证容器拿到新值
docker compose -f docker-compose.prod.yml exec watermirror sh -c 'echo $AUTHING_APP_ID'
```

| 改动了 | 用什么命令 |
|---|---|
| 只是想重启容器（无配置改动） | `docker compose restart` |
| 改了 `.env`（任何 server 端变量） | **`docker compose down && up -d`**（必须重建容器） |
| 改了 `NEXT_PUBLIC_*` env | **必须重新 build 镜像 + push + pull**（值烧在客户端 bundle） |
| 改了代码 | Mac 上 `./push.sh` → ECS `./update.sh` |
| 拉新镜像 | `docker compose -f docker-compose.prod.yml up -d`（自动检测镜像变化） |

**口诀**：改 `.env` 就 `down + up`，比 `restart` 万无一失。

---

## 5. nginx + HTTPS（一条命令搞定两个域名）

### 5.1 一次性配置

确认 toolbox 和 watermirror 容器都已启动，然后：

```bash
ssh deploy@116.62.53.22
cd /opt/toolbox

sudo ./deploy/setup-nginx.sh --https you@example.com
```

脚本做的事：
1. 装 nginx + certbot
2. 部署 `deploy/nginx/{toolbox,watermirror}.conf` 到 `/etc/nginx/sites-available/`
3. 启用两个 vhost、移除 default site
4. `nginx -t` 校验后 reload
5. certbot 给两个子域名同时申请 Let's Encrypt 证书 + 80→443 自动跳转 + 装续期 timer
6. 健康检查 5000 / 3000 后端

### 5.2 验证

```bash
# Mac 上
dig +short toolbox.droplets.com.cn        # 应返回 116.62.53.22
dig +short watermirror.droplets.com.cn

curl -I https://toolbox.droplets.com.cn        # 200 / 302
curl -I https://watermirror.droplets.com.cn

# 浏览器隐身模式打开两个域名，看到登录页 = OK
```

### 5.3 nginx 配置文件结构

```
/etc/nginx/sites-available/
├── toolbox.conf         # toolbox.droplets.com.cn → 127.0.0.1:5000
└── watermirror.conf     # watermirror.droplets.com.cn → 127.0.0.1:3000

/etc/nginx/sites-enabled/   # 软链到 sites-available 同名文件
```

certbot 自动改的部分（在 .conf 里）：
- `listen 443 ssl http2;`
- `ssl_certificate /etc/letsencrypt/live/<domain>/fullchain.pem;`
- `ssl_certificate_key /etc/letsencrypt/live/<domain>/privkey.pem;`
- 80 → 443 重定向块

### 5.4 证书续期

certbot 自动装了 systemd timer，每天检查、剩余 < 30 天自动续。

```bash
# 看续期状态
sudo systemctl list-timers | grep certbot
sudo certbot certificates

# 手动测试续期（不真续）
sudo certbot renew --dry-run
```

---

## 6. 数据备份

### 6.1 toolbox 数据备份

```bash
# 手动备份一份
sudo tar -czf ~/backups/toolbox-$(date +%Y%m%d).tar.gz \
    -C /opt/toolbox docker-data

# 自动每天备份（crontab -e 添加）
0 2 * * * tar -czf /home/deploy/backups/toolbox-$(date +\%Y\%m\%d).tar.gz \
    -C /opt/toolbox docker-data && \
    find /home/deploy/backups -name 'toolbox-*.tar.gz' -mtime +30 -delete
```

恢复：
```bash
docker compose -f /opt/toolbox/docker-compose.yml down
sudo tar -xzf ~/backups/toolbox-20260427.tar.gz -C /opt/toolbox/
docker compose -f /opt/toolbox/docker-compose.yml up -d
```

### 6.2 watermirror 数据备份

数据在云端，不需要本地备份，但可以做：

- **PolarDB**：阿里云控制台 → PolarDB → 备份恢复 → 设置自动备份策略 + 偶尔手动备份
- **OSS**：开启 bucket 的版本控制（防误删）
- **`.env`**：本地保存 `.env.backup.<日期>` 副本（含密钥）

---

## 7. 日常运维 cheat sheet

```bash
# ───── 状态 ─────
docker compose -f /opt/toolbox/docker-compose.yml ps
docker compose -f /opt/waterMirror/docker-compose.prod.yml ps
sudo systemctl status nginx
df -h
free -h

# ───── 日志 ─────
# toolbox
docker compose -f /opt/toolbox/docker-compose.yml logs -f --tail=80

# watermirror
docker compose -f /opt/waterMirror/docker-compose.prod.yml logs -f --tail=80

# nginx 访问 / 错误
sudo tail -f /var/log/nginx/toolbox.access.log
sudo tail -f /var/log/nginx/watermirror.error.log

# ───── 更新代码 ─────
# toolbox（在 ECS build）
cd /opt/toolbox && git pull && docker compose up -d --build

# watermirror（先 Mac push 再 ECS pull）
# Mac:
cd /Users/vibrant-wellness/waterMirror && ./push.sh watermirror
# ECS:
cd /opt/waterMirror && ./update.sh

# ───── 重启 ─────
# toolbox
cd /opt/toolbox && docker compose restart

# watermirror（仅改 .env 后必须 down+up）
cd /opt/waterMirror
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d

# nginx
sudo nginx -t && sudo systemctl reload nginx

# ───── 进容器调试 ─────
docker compose -f /opt/toolbox/docker-compose.yml exec toolbox sh
docker compose -f /opt/waterMirror/docker-compose.prod.yml exec watermirror sh

# ───── 证书 ─────
sudo certbot certificates
sudo certbot renew --dry-run

# ───── 磁盘 / 镜像清理 ─────
docker image prune -f                  # 清无标签镜像
docker system prune -f                 # 清无用资源（不删数据）
sudo du -h --max-depth=1 / | sort -hr | head -10  # 看大目录

# ───── 备份 ─────
sudo tar -czf ~/backups/toolbox-$(date +%Y%m%d).tar.gz -C /opt/toolbox docker-data
```

---

## 8. 常见坑速查

| 现象 | 原因 | 解决 |
|---|---|---|
| `docker pull` 报 `404 Not Found` | 阿里云免费 mirror 已退化 | 跑 `sudo ./deploy/setup-docker.sh` 配多 mirror |
| `docker pull` 超时（i/o timeout） | docker.io 国内被墙 + 没配 mirror | 同上 |
| `failed to resolve docker.io/docker/dockerfile:1.6` | Dockerfile 头部 `# syntax=` 拉不到 | 删掉那行（toolbox 已修复） |
| 浏览器看到 IIS 风格 404 | 域名敲错（漏 `.cn` 之类） | 确认完整域名 `toolbox.droplets.com.cn` |
| 浏览器 502 Bad Gateway | 后端容器没起 / 端口不对 | `docker compose ps` 看状态，`docker logs` 看错误 |
| certbot 报"Timeout during connect" | 安全组没开 80 | 阿里云安全组入方向加 TCP 80 |
| Flask 报 `no secret key was set` | secret_key 文件是空的（旧 entrypoint bug） | `sudo bash -c 'openssl rand -hex 32 > /opt/toolbox/docker-data/secret_key' && docker compose restart toolbox` |
| watermirror DB `pg_hba.conf rejected` | ECS IP 不在 PolarDB 白名单 | PolarDB 控制台 → 白名单 → 加 ECS 内网 IP |
| 改 `.env` 后值没生效 | `docker compose restart` 不重读 .env | 用 `down + up -d` 强制重建容器 |
| 改 `NEXT_PUBLIC_*` 后值没生效 | 这类变量烧在客户端 bundle 里 | 必须重新 build + push + pull 镜像 |
| Authing 报 `redirect_uri 不在白名单` | Authing 后台没加生产回调 URL | Authing 控制台 → 应用 → 加 `https://watermirror.droplets.com.cn/api/auth/callback` |
| 容器频繁重启 | 看日志找根因 | `docker compose logs --tail=100 <service>` |
| 容器 `unhealthy` 但应用可用 | healthcheck 命中的 endpoint 返回非 200 | 给应用加 `/api/health` 返回 200，改 healthcheck 用它 |
| Mac 端 push 失败 401 | docker login 凭证过期 | 重新 `docker login --username=bchg4 crpi-...personal.cr.aliyuncs.com` |
| ECS 端 OOM | 在 ECS 直接 build watermirror | 严禁，必须本地 build → ACR → ECS pull |

---

## 9. 端口与文件总览

```
┌─ ECS 服务器 ────────────────────────────────────────────────────────┐
│                                                                     │
│  公网入口:                                                          │
│  ├─ 22  (SSH)                                                       │
│  ├─ 80  (nginx — 重定向到 443)                                      │
│  └─ 443 (nginx — HTTPS)                                             │
│                                                                     │
│  本机内部端口（127.0.0.1 only，不开放公网）:                        │
│  ├─ 5000 → toolbox 容器                                             │
│  └─ 3000 → watermirror 容器                                         │
│                                                                     │
│  关键路径:                                                          │
│  ├─ /opt/toolbox/                                                   │
│  │  ├─ docker-compose.yml      (本地 build 模式)                    │
│  │  ├─ Dockerfile                                                   │
│  │  ├─ docker-entrypoint.sh                                         │
│  │  ├─ docker-data/            ← 持久化数据                         │
│  │  └─ deploy/                                                      │
│  │     ├─ setup-docker.sh      (装 docker + mirror)                 │
│  │     ├─ setup-nginx.sh       (装 nginx + HTTPS)                   │
│  │     └─ nginx/{toolbox,watermirror}.conf                          │
│  │                                                                  │
│  ├─ /opt/waterMirror/                                               │
│  │  ├─ docker-compose.yml      (开发用，本地 build)                 │
│  │  ├─ docker-compose.prod.yml (生产用，拉 ACR 镜像) ← ECS 用这个   │
│  │  ├─ Dockerfile              (本地 build 用)                      │
│  │  ├─ push.sh                 (Mac 端 build + push 到 ACR)         │
│  │  ├─ update.sh               (ECS 端一键更新)                     │
│  │  ├─ .env                    (生产配置，不入 git)                 │
│  │  └─ .env.production         (生产模板，入 git，但 gitignore 真值) │
│  │                                                                  │
│  ├─ /etc/nginx/sites-available/{toolbox,watermirror}.conf           │
│  ├─ /etc/letsencrypt/live/<domain>/{fullchain,privkey}.pem          │
│  └─ /home/deploy/backups/      ← cron 自动备份                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 10. 完整部署 checklist（首次上线时按顺序勾）

```
环境准备
├─ [ ] 阿里云 DNS 加 toolbox 和 watermirror 子域名 A 记录
├─ [ ] ECS 安全组入方向开 22/80/443
├─ [ ] PolarDB 白名单加 ECS 内网 IP
├─ [ ] ACR 个人实例启用 + 创建命名空间 watermirror + 设登录密码
├─ [ ] Authing 应用加生产回调 URL
└─ [ ] OSS bucket 配 CORS

ECS 系统
├─ [ ] SSH 进 ECS，创建 deploy 用户
├─ [ ] 时区改为 Asia/Shanghai
├─ [ ] git clone toolbox 到 /opt/toolbox
├─ [ ] 跑 sudo ./deploy/setup-docker.sh --install
├─ [ ] usermod -aG docker deploy + 重连
└─ [ ] docker info 看 mirror 已加载

toolbox
├─ [ ] cd /opt/toolbox && docker compose up -d --build
├─ [ ] curl http://127.0.0.1:5000/login 返回 200
└─ [ ] (后续可选) 配 cron 每天备份 docker-data/

watermirror
├─ [ ] git clone 到 /opt/waterMirror
├─ [ ] cp .env.production .env (确认所有字段填对)
├─ [ ] docker login ACR
├─ [ ] Mac 端 docker login ACR + ./push.sh watermirror 第一次推送
├─ [ ] ECS 端 docker compose -f docker-compose.prod.yml up -d
├─ [ ] curl http://127.0.0.1:3000/ 返回 200/307
└─ [ ] 容器内 echo $AUTHING_APP_ID 是新值

nginx + HTTPS
├─ [ ] cd /opt/toolbox && sudo ./deploy/setup-nginx.sh --https you@mail.com
├─ [ ] curl -I https://toolbox.droplets.com.cn → 200/302
├─ [ ] curl -I https://watermirror.droplets.com.cn → 200/307
└─ [ ] 浏览器隐身模式打开两个域名，看到正确页面

收尾
├─ [ ] 测一遍登录流程（Authing 跳转、回调、session）
├─ [ ] 测一遍流程图编辑、版本历史、节点附件上传
├─ [ ] 测一遍 watermirror 创建面试 / 上传简历
└─ [ ] crontab 加自动备份
```
