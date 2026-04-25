#!/usr/bin/env bash
# 一键给中国大陆服务器配置 Docker + 多镜像加速器。
#
# 用法（在服务器上以 sudo 跑）：
#   sudo ./deploy/setup-docker.sh                    # 仅写 mirror 配置（假设 Docker 已装）
#   sudo ./deploy/setup-docker.sh --install          # 同时装 Docker（Ubuntu/Debian）
#
# 功能：
#   1. （可选）通过阿里云 apt mirror 安装 docker-ce + compose-plugin
#   2. 写 /etc/docker/daemon.json，配多个国内镜像加速器（自动 fallback）
#   3. 探测各 mirror 可达性，把通的排前面
#   4. systemctl restart docker
#   5. 拉一个小镜像验证

set -euo pipefail

# ---- 候选镜像加速器列表（按优先级，会自动测连通性后排序）----
CANDIDATE_MIRRORS=(
    "https://docker.m.daocloud.io"
    "https://dockerproxy.com"
    "https://docker.nju.edu.cn"
    "https://mirror.baidubce.com"
    "https://docker.1panel.live"
    "https://hub.rat.dev"
)

DAEMON_JSON=/etc/docker/daemon.json
INSTALL_DOCKER=0

# ---- 解析参数 ----
while [[ $# -gt 0 ]]; do
    case "$1" in
        --install)
            INSTALL_DOCKER=1
            shift
            ;;
        -h|--help)
            sed -n '2,12p' "$0"
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

# ---- (可选) 装 Docker ----
if [[ $INSTALL_DOCKER -eq 1 ]]; then
    if command -v docker >/dev/null 2>&1; then
        echo "==> Docker 已安装，跳过安装步骤"
    else
        echo "==> 通过阿里云 apt mirror 安装 Docker ..."
        apt-get update
        apt-get install -y ca-certificates curl gnupg lsb-release

        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg \
            | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        chmod a+r /etc/apt/keyrings/docker.gpg

        codename=$(. /etc/os-release && echo "$VERSION_CODENAME")
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://mirrors.aliyun.com/docker-ce/linux/ubuntu $codename stable" \
            > /etc/apt/sources.list.d/docker.list

        apt-get update
        apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

        systemctl enable docker
        systemctl start docker
    fi
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "未检测到 docker，先用 --install 安装，或手动安装后再跑此脚本" >&2
    exit 1
fi

# ---- 探测 mirror 可达性 ----
echo "==> 探测候选 mirror 可达性 ..."
declare -a OK_MIRRORS=()
declare -a FAILED_MIRRORS=()
for m in "${CANDIDATE_MIRRORS[@]}"; do
    host=${m#https://}
    if curl -fsS -m 5 "$m/v2/" -o /dev/null 2>&1; then
        echo "  ✓ $host"
        OK_MIRRORS+=("$m")
    else
        echo "  ✗ $host"
        FAILED_MIRRORS+=("$m")
    fi
done

# 把通的排前，未通的排后（万一暂时性故障，留作 fallback）
FINAL_MIRRORS=("${OK_MIRRORS[@]}" "${FAILED_MIRRORS[@]}")

if [[ ${#OK_MIRRORS[@]} -eq 0 ]]; then
    echo
    echo "⚠️  所有候选 mirror 都不通。可能原因：" >&2
    echo "   - 服务器没有公网出口（检查阿里云安全组出方向）" >&2
    echo "   - DNS 故障（试 cat /etc/resolv.conf 和 dig docker.m.daocloud.io）" >&2
    echo "   - 这些 mirror 临时维护中" >&2
    echo
    echo "继续写配置（也许后续 mirror 恢复就能用）..."
fi

# ---- 写 daemon.json ----
echo "==> 写 $DAEMON_JSON ..."
mkdir -p /etc/docker

# 备份现有配置（如有）
if [[ -f $DAEMON_JSON ]]; then
    cp -p "$DAEMON_JSON" "$DAEMON_JSON.bak.$(date +%Y%m%d-%H%M%S)"
    echo "  - 已备份原配置到 $DAEMON_JSON.bak.*"
fi

# 用 python 安全合并：保留现有键，覆盖 registry-mirrors
python3 - "$DAEMON_JSON" "${FINAL_MIRRORS[@]}" <<'PY'
import json, sys, os
path = sys.argv[1]
mirrors = sys.argv[2:]
cfg = {}
if os.path.exists(path):
    try:
        with open(path) as f:
            cfg = json.load(f) or {}
    except Exception:
        cfg = {}
cfg["registry-mirrors"] = mirrors
# 顺手加几条好习惯默认值（如果用户没配过）
cfg.setdefault("log-driver", "json-file")
cfg.setdefault("log-opts", {"max-size": "10m", "max-file": "3"})
with open(path + ".tmp", "w") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
os.replace(path + ".tmp", path)
print(f"写入 {len(mirrors)} 个 mirror")
PY

# 校验 JSON
python3 -c "import json; json.load(open('$DAEMON_JSON'))" \
    || { echo "❌ daemon.json 不是合法 JSON！请检查 $DAEMON_JSON" >&2; exit 1; }

# ---- 重启 docker ----
echo "==> 重启 docker daemon ..."
systemctl daemon-reload
systemctl restart docker
sleep 2

# ---- 验证 ----
echo "==> 验证 mirror 已加载 ..."
docker info 2>/dev/null | grep -A "${#FINAL_MIRRORS[@]}" "Registry Mirrors" || true

echo
echo "==> 拉一个小镜像验证 ..."
if docker pull hello-world:latest >/dev/null 2>&1; then
    echo "  ✓ docker pull hello-world 成功"
    docker rmi hello-world:latest >/dev/null 2>&1 || true
else
    echo "  ✗ docker pull hello-world 失败"
    echo "    试试手动: docker pull hello-world"
    echo "    或看日志: sudo journalctl -u docker.service -n 50 --no-pager"
fi

echo
echo "=========================================="
echo " ✅ Docker 镜像加速配置完成"
echo "=========================================="
echo " 通的 mirror：${#OK_MIRRORS[@]}/${#CANDIDATE_MIRRORS[@]}"
for m in "${OK_MIRRORS[@]}"; do echo "   ✓ $m"; done
echo
echo " 配置文件：$DAEMON_JSON"
echo " 接下来：cd ~/toolbox && docker compose up -d --build"
