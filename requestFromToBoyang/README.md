# 我觉得系统应该是这样的 !

团队内部需求收集工具，支持局域网访问。任何人打开页面就能提需求、点赞、评论，管理员可以在线更新进度状态。

---

## 快速启动

三个脚本功能完全相同，按系统选一个即可：

| 系统 | 文件 | 方式 |
|------|------|------|
| macOS / Linux | `run.sh` | 终端执行 `./run.sh` |
| Windows（推荐） | `run.bat` | 双击文件 / CMD 执行 |
| Windows（PowerShell） | `run.ps1` | 右键「用 PowerShell 运行」|

**macOS / Linux**
```bash
cd requestFromToBoyang
./run.sh
```

**Windows CMD**
```bat
双击 run.bat
```
或在 CMD 中：
```bat
cd requestFromToBoyang
run.bat
```

**Windows PowerShell**（首次需要解除执行策略限制）
```powershell
# 仅首次，管理员身份运行一次：
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 之后每次右键「用 PowerShell 运行」run.ps1 即可
```

脚本会自动：
1. 创建 Python 虚拟环境 `.venv`
2. 安装 Flask 依赖
3. 启动服务并打印访问地址

启动后终端输出示例：

```
==================================================
 我觉得系统应该是这样的 !
==================================================
 本机访问:  http://127.0.0.1:5000
 局域网访问: http://192.168.1.88:5000
==================================================
```

把局域网地址发给同事即可，无需任何客户端安装。

---

## 功能说明

| 页面 | 路径 | 说明 |
|------|------|------|
| 提交需求 | `/` | 填写标题、内容、上传人（必填），可附一张图片 |
| 需求列表 | `/requirements` | 所有需求倒序排列，显示状态、点赞数、评论数 |
| 需求详情 | `/requirements/<id>` | 完整内容 + 大图、点赞、更新进度、查看/发表评论 |

### 进度状态

| 标签 | 含义 |
|------|------|
| 🟡 待处理 | 默认状态，尚未开始 |
| 🔵 进行中 | 已排期开发 |
| 🟢 已完成 | 功能已上线 |
| ⚫ 已搁置 | 暂不处理 |

在详情页下拉选择后点「保存」即可更新，所有人可见。

### 名字记忆（Session）

- 第一次填写名字并提交需求或发表评论后，名字自动保存到浏览器 Session。
- 之后访问提交表单、评论框时，名字会**自动填入**，无需重复输入。
- Session 有效期 **30 天**，到期或清除浏览器 Cookie 后会重置。
- 不同设备/浏览器各自独立，互不影响。

---

## 数据存储

| 路径 | 内容 |
|------|------|
| `data.db` | SQLite 数据库，存储所有需求、评论、点赞数 |
| `uploads/` | 用户上传的图片，以 UUID 命名 |
| `.secret_key` | Flask Session 签名密钥，自动生成并持久化，重启后 Session 不失效 |

> `data.db` 和 `uploads/` 均在首次启动时自动创建，无需手动操作。

### 查看原始数据

```bash
# 查看所有需求（含 IP 地址）
sqlite3 data.db "SELECT id, created_at, author, ip, title FROM requirements ORDER BY id DESC;"

# 查看所有评论（含 IP 地址）
sqlite3 data.db "SELECT id, requirement_id, created_at, author, ip FROM comments ORDER BY id DESC;"
```

---

## IP 记录

每次用户**提交需求**或**发表评论**时，后台会自动记录客户端 IP 地址：

- 存入数据库对应记录的 `ip` 字段
- 同时打印到终端日志，格式如下：

```
[2025-04-11 14:22:01] SUBMIT requirement from 192.168.1.42 id=5 author='张三' title='优化登录页面'
[2025-04-11 14:25:30] COMMENT from 192.168.1.55 rid=5 author='李四'
```

IP 地址**不会展示给普通访问者**，仅供后台管理使用。

---

## 图片上传限制

- 最大单文件：**16 MB**
- 支持格式：`png` / `jpg` / `jpeg` / `gif` / `webp` / `bmp`

---

## 目录结构

```
requestFromToBoyang/
├── app.py              # Flask 后端主文件
├── requirements.txt    # Python 依赖（仅 Flask）
├── run.sh              # 一键启动脚本
├── templates/
│   ├── base.html       # 公共布局
│   ├── index.html      # 提交需求页
│   ├── list.html       # 需求列表页
│   └── detail.html     # 需求详情 + 评论页
├── static/
│   └── style.css       # 样式
├── uploads/            # 上传图片（自动创建）
├── data.db             # SQLite 数据库（自动创建）
└── .secret_key         # Session 密钥（自动生成）
```

---

## 依赖环境

- Python 3.8+
- Flask 2.3+（由 `run.sh` 自动安装，无需手动操作）

---

## macOS 防火墙提示

首次局域网访问时 macOS 可能弹出防火墙授权窗口，选择「允许」即可。
