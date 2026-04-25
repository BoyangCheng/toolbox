#!/usr/bin/env bash
# 一键给 droplets.com.cn 下的两个子域名（toolbox / watermirror）配置 nginx 反代 + HTTPS。
#
# 用法（在服务器上以 sudo 跑）：
#   cd /path/to/toolbox-repo
#   sudo ./deploy/setup-nginx.sh                    # 仅装 HTTP，不申请 HTTPS
#   sudo ./deploy/setup-nginx.sh --https you@mail   # 同时申请 HTTPS（邮箱用于 Let's Encrypt 通知）
#
# 前置条件：
#   1. DNS 已经解析（toolbox / watermirror 两个 A 记录指向本机公网 IP）
#   2. 阿里云安全组开放 80 + 443
#   3. 后端服务已启动: toolbox 在 :5000, watermirror 在 :3000
#   4. 域名已 ICP 备案（如服务器在国内）

set -euo pipefail

DOMAINS=(
    "toolbox.droplets.com.cn"
    "watermirror.droplets.com.cn"
)
CONF_NAMES=(
    "toolbox.conf"
    "watermirror.conf"
)

EMAIL=""
ENABLE_HTTPS=0

# ---- 解析参数 ----
while [[ $# -gt 0 ]]; do
    case "$1" in
        --https)
            ENABLE_HTTPS=1
            EMAIL="${2:-}"
            shift 2
            ;;
        -h|--help)
            sed -n '2,15p' "$0"
            exit 0
            ;;
        *)
            echo "未知参数: $1" >&2
            exit 1
            ;;
    esac
done

if [[ $EUID -ne 0 ]]; then
    echo "请用 sudo 运行" >&2
    exit 1
fi

if [[ $ENABLE_HTTPS -eq 1 && -z "$EMAIL" ]]; then
    echo "--https 后必须跟邮箱（Let's Encrypt 通知用）" >&2
    exit 1
fi

# ---- 找配置文件源 ----
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
NGINX_SRC="$SCRIPT_DIR/nginx"

for f in "${CONF_NAMES[@]}"; do
    if [[ ! -f "$NGINX_SRC/$f" ]]; then
        echo "找不到 $NGINX_SRC/$f，请确认你在 toolbox 仓库根目录运行此脚本。" >&2
        exit 1
    fi
done

# ---- 安装依赖 ----
echo "==> 检查并安装 nginx ..."
if ! command -v nginx >/dev/null 2>&1; then
    apt-get update
    apt-get install -y nginx
fi

if [[ $ENABLE_HTTPS -eq 1 ]]; then
    echo "==> 检查并安装 certbot ..."
    if ! command -v certbot >/dev/null 2>&1; then
        apt-get install -y certbot python3-certbot-nginx
    fi
fi

# ---- 拷贝配置 ----
echo "==> 部署 nginx vhost ..."
mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
for f in "${CONF_NAMES[@]}"; do
    cp -v "$NGINX_SRC/$f" "/etc/nginx/sites-available/$f"
    ln -sfn "/etc/nginx/sites-available/$f" "/etc/nginx/sites-enabled/$f"
done

# 移除 default site（如存在），避免抢占未匹配请求
if [[ -L /etc/nginx/sites-enabled/default ]]; then
    rm -f /etc/nginx/sites-enabled/default
    echo "  - 移除 default site"
fi

# ---- 校验 + 重载 ----
echo "==> 校验 nginx 配置 ..."
nginx -t

echo "==> 重载 nginx ..."
systemctl reload nginx
systemctl enable nginx >/dev/null 2>&1 || true

# ---- HTTPS ----
if [[ $ENABLE_HTTPS -eq 1 ]]; then
    echo "==> 通过 certbot 申请 HTTPS 证书 ..."
    certbot_args=(--nginx --non-interactive --agree-tos --redirect -m "$EMAIL")
    for d in "${DOMAINS[@]}"; do
        certbot_args+=(-d "$d")
    done
    certbot "${certbot_args[@]}"
    echo "==> 验证自动续期 ..."
    certbot renew --dry-run
fi

# ---- 健康检查 ----
echo "==> 验证后端 ..."
for port in 5000 3000; do
    if curl -fsSI "http://127.0.0.1:$port/" >/dev/null 2>&1 || \
       curl -fsSI "http://127.0.0.1:$port/login" >/dev/null 2>&1 ; then
        echo "  ✓ 127.0.0.1:$port 响应正常"
    else
        echo "  ⚠ 127.0.0.1:$port 没响应 — 先把对应后端服务启动起来"
    fi
done

echo
echo "=========================================="
echo " ✅ 部署完成"
echo "=========================================="
for d in "${DOMAINS[@]}"; do
    if [[ $ENABLE_HTTPS -eq 1 ]]; then
        echo "  https://$d"
    else
        echo "  http://$d"
    fi
done
echo
echo "日志: /var/log/nginx/{toolbox,watermirror}.{access,error}.log"
