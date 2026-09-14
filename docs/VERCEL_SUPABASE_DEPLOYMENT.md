# MMS 部署指南：Vercel + Supabase

本文适用于将当前 Django MMS 发布到 `yqnus.com`。Supabase 只承担 PostgreSQL 和私有文件存储；用户登录、权限和会话仍由 Django 管理，不使用 Supabase Auth。

## 1. 部署结构

- Vercel：运行 Django WSGI、静态文件和每分钟周期扫描。
- Supabase Database：保存用户、仓库、设备、工单、通知和会话。
- Supabase Storage：保存任务照片、附件和设备导入源文件。
- `yqnus.com`：正式入口；`www.yqnus.com` 重定向到根域名。

Vercel Hobby 的 Cron 最多每天一次，而且仅限非商业个人项目。本系统的 `vercel.json` 使用每分钟调度，因此应使用 Vercel Pro。

## 2. 创建 Supabase 项目

1. 在 Supabase 新建项目，选择靠近主要仓库和 Vercel 函数的美国区域。
2. 保存数据库密码，不要在 GitHub、聊天或前端代码中公开。
3. 打开项目的数据库连接页面，记录两条连接：
   - Vercel 运行时使用 Transaction pooler，通常为端口 `6543`。
   - 首次迁移可使用 Session pooler 或 Direct connection，通常为端口 `5432`。
4. 连接 URI 必须带 `sslmode=require`。如果密码含有 `@`、`:`、`/`、`#` 等字符，先进行 URL 编码。

Vercel 中的形式类似：

```text
postgresql://postgres.PROJECT_REF:URL_ENCODED_PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres?sslmode=require
```

不要使用浏览器端的 Supabase anon key 代替数据库连接密码。

## 3. 创建私有 Storage

1. 在 Supabase Storage 新建私有 bucket：`mms-media`。
2. 在 Storage 的 S3 配置页面创建 S3 Access Key。
3. 记录 Access Key ID、Secret Access Key、项目 Region 和 S3 Endpoint。
4. 不要将 bucket 改成 public。Django 会生成有效期 5 分钟的签名查看地址。

S3 Endpoint 的形式通常是：

```text
https://PROJECT_REF.storage.supabase.co/storage/v1/s3
```

这些 S3 凭证只能放在 Vercel 服务端环境变量中，不能以 `NEXT_PUBLIC_` 或其他前端变量形式公开。

## 4. 上传到私有 GitHub 仓库

在项目根目录初始化 Git，并确认忽略规则生效：

```powershell
git init
git add .
git status
```

`git status` 中不应出现以下内容：

- `db.sqlite3`
- `media/`
- `backups/`
- `.env` 或任何包含真实密钥的文件
- `.venv/`

确认后提交并推送到 GitHub 私有仓库。源码中原有的管理员密码注释已经删除；正式数据库仍应设置独立的强管理员密码。

## 5. 在 Vercel 导入项目

1. 在 Vercel 选择 **Add New → Project**。
2. 导入上一步的 GitHub 私有仓库。
3. Root Directory 选择包含 `manage.py` 的项目根目录。
4. Framework Preset 让 Vercel自动识别 Django。
5. 不要填写自动执行 `migrate` 的 Build Command。数据库迁移应该在发布前单独执行，避免多个构建并发迁移。

Vercel 会读取 `.python-version` 使用 Python 3.12，并自动识别 `config/wsgi.py`。静态文件会在构建阶段自动收集。

## 6. 配置 Vercel 环境变量

在 **Project → Settings → Environment Variables** 添加以下变量，先只应用于 Production。Preview 应使用独立的 Supabase 项目和 bucket，或者暂时关闭预览部署，不能让预览环境写入正式数据。

```dotenv
MMS_DEBUG=0
MMS_SECRET_KEY=<独立生成的长随机值>
MMS_ALLOWED_HOSTS=yqnus.com,www.yqnus.com,.vercel.app
MMS_CSRF_TRUSTED_ORIGINS=https://yqnus.com,https://www.yqnus.com,https://*.vercel.app
MMS_SECURE_SSL_REDIRECT=1
MMS_SECURE_HSTS_SECONDS=3600

DATABASE_URL=<Supabase Transaction pooler URI，端口通常为 6543>
MMS_DATABASE_POOL_MODE=transaction

MMS_STORAGE_BACKEND=supabase
MMS_STORAGE_PREFIX=media
AWS_ACCESS_KEY_ID=<Supabase Storage S3 Access Key ID>
AWS_SECRET_ACCESS_KEY=<Supabase Storage S3 Secret Access Key>
AWS_STORAGE_BUCKET_NAME=mms-media
AWS_S3_ENDPOINT_URL=https://PROJECT_REF.storage.supabase.co/storage/v1/s3
AWS_S3_REGION_NAME=<Supabase 项目 Region>

CRON_SECRET=<另一个独立的长随机值>
MMS_CRON_MAX_OCCURRENCES=100
MMS_LOCAL_SCHEDULER=0
```

在本地生成两个不同的随机密钥：

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

第一个作为 `MMS_SECRET_KEY`，第二个作为 `CRON_SECRET`。Vercel 会自动把 `CRON_SECRET` 以 `Authorization: Bearer ...` 发送给调度接口。

## 7. 初始化 Supabase 数据库

第一次发布前，在本地 PowerShell 临时连接 Supabase 的 Session pooler 或 Direct connection：

```powershell
$env:DATABASE_URL = "<Supabase 迁移连接 URI，带 sslmode=require>"
$env:MMS_DATABASE_POOL_MODE = "session"
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py check --deploy
Remove-Item Env:DATABASE_URL
Remove-Item Env:MMS_DATABASE_POOL_MODE
```

`check --deploy` 中关于当前仍处于 Debug 的提示可以通过在该终端临时设置完整生产变量复查。不要运行 `seed_demo`，除非确实需要演示数据。

默认不会开启 `SECURE_HSTS_INCLUDE_SUBDOMAINS` 和 `SECURE_HSTS_PRELOAD`，因此 `check --deploy` 会保留对应两条提示。这是有意的：只有确认 `yqnus.com` 的所有子域名现在及以后都只使用 HTTPS，且理解浏览器预加载难以撤销后，才应设置 `MMS_SECURE_HSTS_INCLUDE_SUBDOMAINS=1` 和 `MMS_SECURE_HSTS_PRELOAD=1`。

以上步骤建立一个全新的生产数据库。不要上传 `db.sqlite3` 到 Vercel，它在无服务器文件系统中不会持久保存。

如需保留当前本地 SQLite 数据，应先备份，再进行一次单独的数据迁移。建议在新数据库完成结构迁移后使用 Django `dumpdata`/`loaddata`，并逐项核对用户、角色、仓库、设备、工单和通知数量。已有 `media/` 文件还需要另行上传到 `mms-media`，不能只迁移数据库记录。

## 8. 部署和 Cron

触发 Vercel Production Deployment。`vercel.json` 已配置：

- Django 函数最长运行 60 秒。
- 每分钟请求 `/internal/cron/work-orders/`。

调度接口只接受带正确 Bearer 密钥的 GET 请求，不会开放给普通用户。每次最多处理 100 个到期期次；如果停机期间积压超过 100 个，下一分钟继续补齐。数据库行锁和唯一约束会防止同一期重复生成。

部署完成后在 **Project → Cron Jobs** 确认任务存在，并在 Runtime Logs 中确认接口返回 HTTP 200。不要在 Vercel 中运行常驻的 `run_workorder_scheduler`、Celery Worker 或本地 `runserver` 调度线程。

## 9. 绑定 yqnus.com

1. 打开 Vercel **Project → Settings → Domains**。
2. 添加 `yqnus.com` 和 `www.yqnus.com`。
3. 将 `www.yqnus.com` 设置为重定向到 `yqnus.com`。
4. 在域名 DNS 服务商处，严格按 Vercel 页面给出的值配置：
   - 根域名 `@` 通常使用 A 记录。
   - `www` 通常使用 CNAME。
   - 若提示所有权验证，再添加对应 TXT。
5. 删除同一主机名上冲突的旧 A、AAAA 或 CNAME，但不要删除邮箱使用的 MX、SPF、DKIM 和其他 TXT。
6. 等待 Vercel 显示 Valid Configuration 和 HTTPS 证书就绪。

不要照抄其他项目的 Vercel IP 或 CNAME，项目页面显示的值才是准确信息。

## 10. 上线验收

按顺序检查：

1. `https://yqnus.com/login/` 可以打开并通过 HTTPS 登录。
2. `/admin/` 可以登录，普通用户不能越权访问其他仓库。
3. 创建一次性工单后，工作台、通知和详情显示正确。
4. 创建一个几分钟后到期的周期工单，在 Cron Logs 中看到扫描成功，并只生成一个后续期次。
5. 分别选择美东、美中、美西，确认生成时间和剩余时间正确。
6. 上传小于 4 MB 的 JPG、PNG 或 WebP，刷新和重新部署后仍可查看。
7. 上传 CSV/XLSX 并执行设备导入。
8. 导出日报和周报。
9. 检查 Supabase 数据库备份、Vercel/Supabase 用量告警和运行错误日志。

Vercel 请求体上限为 4.5 MB，因此本项目把任务照片和导入文件限制为 4 MB，预留 multipart 请求开销。需要支持更大文件时，应改为浏览器直传 Supabase Storage，而不是提高 Django 限制。
