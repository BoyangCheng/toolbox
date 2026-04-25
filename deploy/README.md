# 部署辅助文件

```
deploy/
├── nginx/
│   ├── toolbox.conf        # toolbox.droplets.com.cn → 127.0.0.1:5000
│   └── watermirror.conf    # watermirror.droplets.com.cn → 127.0.0.1:3000
├── setup-docker.sh         # 一键装 Docker + 配多镜像加速器（国内必备）
├── setup-nginx.sh          # 一键部署 nginx + 申请 HTTPS
└── README.md               # 本文件
```

## 多子域名共用一台服务器的部署流程

适用场景：同一台阿里云 ECS 上跑多个服务，用不同子域名区分。

### 1. 阿里云 DNS 解析

控制台 → 云解析 DNS → `droplets.com.cn` → 解析设置，添加：

| 主机记录 | 类型 | 记录值 | TTL |
|---|---|---|---|
| `toolbox` | A | 服务器公网 IP | 600 |
| `watermirror` | A | 服务器公网 IP | 600 |

> `.cn` 域名指向中国大陆服务器需主域名已 ICP 备案，子域名继承备案。

### 2. 阿里云安全组

ECS 实例 → 安全组规则 → 入方向开放 TCP **80**、**443**。
后端服务端口（5000、3000）**不开放公网**，全部走 nginx。

### 3. 启动后端服务

- toolbox：见 [仓库根 README](../README.md)，监听 `127.0.0.1:5000`
- watermirror：按其自己的 README 部署，监听 `127.0.0.1:3000`

确认本机能访问：

```bash
curl -sI http://127.0.0.1:5000/login
curl -sI http://127.0.0.1:3000/
```

### 4. 一键配 nginx + HTTPS

在仓库根目录运行：

```bash
# 仅 HTTP（先确认 DNS 已生效再做 HTTPS）
sudo ./deploy/setup-nginx.sh

# 一并申请 HTTPS（推荐）
sudo ./deploy/setup-nginx.sh --https you@your-mail.com
```

脚本会：

1. 装 nginx（如未装）
2. 拷 `nginx/*.conf` 到 `/etc/nginx/sites-available/` 并启用
3. 移除 default site
4. `nginx -t` 校验后 reload
5. （可选）certbot 申请 Let's Encrypt 证书 + 自动 80→443 跳转 + 续期任务
6. 健康检查 5000 / 3000 后端

### 5. 验证

```bash
# DNS
dig +short toolbox.droplets.com.cn
dig +short watermirror.droplets.com.cn

# HTTPS 响应
curl -I https://toolbox.droplets.com.cn
curl -I https://watermirror.droplets.com.cn

# 实时看请求
sudo tail -f /var/log/nginx/toolbox.access.log
sudo tail -f /var/log/nginx/watermirror.access.log
```

## 加新的子域名

1. DNS 加一条 A 记录
2. 复制 `nginx/toolbox.conf` 改成新文件，调整 `server_name` 和 `proxy_pass` 端口
3. 把新文件加到 `setup-nginx.sh` 的 `DOMAINS` 和 `CONF_NAMES` 数组
4. 重跑 `sudo ./deploy/setup-nginx.sh --https ...`

## 排错速查

| 现象 | 检查 |
|---|---|
| 浏览器 502 | 后端服务没起 / 端口不对：`ss -tlnp \| grep -E '5000\|3000'` |
| 浏览器 404 + 默认 nginx 页 | default site 没移除：`ls -l /etc/nginx/sites-enabled/` |
| 域名解析不到 | DNS 还没生效：`dig +short <域名>` |
| HTTPS 申请失败 | 80 端口被占 / 安全组没开 / DNS 未生效 |
| `nginx -t` fail | 看 `/etc/nginx/sites-enabled/` 下哪个文件报错，逐个排查 |

---

# 阿里云 ECS 从零部署完整流程

适用：刚买好的阿里云 ECS（Ubuntu 22.04），同一台机器跑 toolbox + watermirror。

## 1. 阿里云控制台

**ECS → 安全组 → 入方向规则**：开放
- TCP `22`（SSH）
- TCP `80`（HTTP）
- TCP `443`（HTTPS）

`5000` / `3000` 不开，nginx 做唯一入口。

**确认主域名 ICP 备案**已通过（"备案"控制台查），子域名继承备案。

## 2. SSH 连接 + 系统初始化

```bash
ssh root@<ECS公网IP>
```

```bash
apt update && apt upgrade -y
apt install -y git curl ufw
timedatectl set-timezone Asia/Shanghai

# 创建非 root 业务用户
useradd -m -s /bin/bash deploy
usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
```

后续 `ssh deploy@<IP>`，`sudo` 提权。

## 3. 装 Docker + 配镜像加速

国内 ECS 必做。一键脚本：

```bash
cd ~
git clone https://github.com/BoyangCheng/toolbox.git
cd toolbox

# 同时安装 Docker + 配多镜像加速
sudo ./deploy/setup-docker.sh --install

# 让 deploy 用户免 sudo 用 docker
sudo usermod -aG docker deploy
# 退出 SSH 重连让 docker 组生效
```

脚本做了这几件事：
1. 通过阿里云 apt mirror 装 docker-ce + buildx + compose-plugin
2. 探测 5 个国内公益 mirror（DaoCloud / dockerproxy / NJU / 百度云 / 1Panel）的连通性
3. 把通的排前面写到 `/etc/docker/daemon.json`，自动 fallback
4. 重启 docker daemon 并拉 hello-world 验证

> **不要只用阿里云免费 mirror**（`xxx.mirror.aliyuncs.com`）—— 它从 2024 年起逐步退化，对常见镜像经常返回 404。脚本里默认用的多 mirror 组合更稳。

如果 Docker 已装好，只需补 mirror 配置：

```bash
sudo ./deploy/setup-docker.sh
```

## 4. 部署 toolbox

```bash
cd ~
git clone https://github.com/BoyangCheng/toolbox.git
cd toolbox
docker compose up -d --build
docker compose logs -f
# 看到 Serving on http://0.0.0.0:5000 即 OK

curl -sI http://127.0.0.1:5000/login
# HTTP/1.1 200 OK + Server: waitress
```

数据持久化在 `~/toolbox/docker-data/`，备份打包这一个目录即可。

## 5. 部署 watermirror

```bash
cd ~
git clone <watermirror-repo-url> waterMirror
cd waterMirror
docker compose up -d --build
curl -sI http://127.0.0.1:3000/
```

> 想限制后端只能本机访问，把 compose 里的 `ports: - "3000:3000"` 改成 `ports: - "127.0.0.1:3000:3000"`。toolbox 同理。

## 6. 配 nginx + HTTPS

```bash
cd ~/toolbox
sudo ./deploy/setup-nginx.sh --https your-email@example.com
```

## 7. 验证

```bash
dig +short toolbox.droplets.com.cn
dig +short watermirror.droplets.com.cn
curl -I https://toolbox.droplets.com.cn
curl -I https://watermirror.droplets.com.cn
sudo tail -f /var/log/nginx/toolbox.access.log
docker compose -f ~/toolbox/docker-compose.yml ps
```

## 8. 日常运维

```bash
# 部署 toolbox 新版本
cd ~/toolbox && git pull && docker compose up -d --build

# 部署 watermirror 新版本
cd ~/waterMirror && git pull && docker compose up -d --build

# 重载 nginx
sudo nginx -t && sudo systemctl reload nginx

# 证书状态
sudo certbot certificates
sudo certbot renew --dry-run

# 备份 toolbox 数据
tar -czf ~/backups/toolbox-$(date +%Y%m%d).tar.gz -C ~/toolbox docker-data/

# 进容器调试
docker compose -f ~/toolbox/docker-compose.yml exec toolbox sh
```

## 9. 常见坑

| 现象 | 原因 / 解决 |
|---|---|
| `docker compose up` 拉镜像慢/404 | 跑 `sudo ./deploy/setup-docker.sh` 配多镜像加速 |
| 域名访问超时 | 安全组没开 80/443，或 DNS 没生效 |
| HTTPS 申请 `Connection refused` | DNS 未生效 / 80 端口被占 |
| 502 Bad Gateway | 后端容器没起 / 端口不对（`docker compose ps`） |
| 容器频繁重启 | `docker compose logs --tail=100 <服务>` 看错误 |
