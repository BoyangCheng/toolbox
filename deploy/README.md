# 部署辅助文件

```
deploy/
├── nginx/
│   ├── toolbox.conf        # toolbox.droplets.com.cn → 127.0.0.1:5000
│   └── watermirror.conf    # watermirror.droplets.com.cn → 127.0.0.1:3000
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
