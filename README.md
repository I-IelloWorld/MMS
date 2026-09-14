# MMS - 仓库自动化设备维保管理系统

这是一个以多仓库为数据边界的 Django 网页项目。当前框架覆盖设备与部件台账、CSV/XLSX 导入、一次性/周期性工单、仓库工程师通知、工单执行和管理后台。

最初版本的需求文档位于 `docs/MMS_需求规格与数据库设计_v1.0.docx`；旧版文档和生成脚本仅供历史参考，当前模型以 `apps/*/models.py` 和已应用迁移为准。

## 已实现的框架能力

- 多仓库、用户仓库成员关系和可配置的仓库角色。
- 自动化设备、设备分类、设备部件层级和关键度。
- CSV/XLSX 设备导入、逐行错误记录和导入批次追踪。
- 直接创建一次性工单或周期性工单，不再维护维保模板和维保计划。
- 到期周期工单幂等生成独立工单，复制任务快照并定向创建站内通知。
- 工单认领、开始、任务完成、提交完成、退回和验收关闭。
- 响应式工作台、设备、工单、导入和消息页面。
- Django Admin 主数据维护，以及 SQLite/PostgreSQL 双数据库配置。
- 用户加入 Django 用户组后自动获得组权限和后台登录资格。
- 仓库角色可在管理后台新增、修改，并可配置接单、管理工单和 Django 权限。
- 支持简体中文、英文和西班牙语切换。
- 不启用密码复杂度校验，允许管理员创建使用简单密码的账号。

## 本地启动

依赖已安装在项目的 `.venv` 中。在 PowerShell 中执行：

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py seed_demo
.\scripts\run-dev.ps1
```

然后访问 [http://127.0.0.1:8000](http://127.0.0.1:8000)。管理后台位于 [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)。

设备导入样例为 `samples/equipment_import_template.csv`。导入前应先在管理后台维护模板中使用的 `category_code`；`seed_demo` 已创建 `CONVEYOR`、`ROBOT` 和 `ASRS` 三个分类。

## 生成周期工单

前台和后台创建工单时均可选择“工单时区”：美东（America/New_York）、美中（America/Chicago）或美西（America/Los_Angeles），默认使用创建人账号的时区。“工单开始生成日期”和“周期结束时间”都按该工单所选时区解析，数据库统一保存 UTC 时间。工单列表、详情、工作台和报表按各自工单的时区显示。

后续期次继承来源工单的时区，按当地日历周期生成，跨夏令时也保持相同的当地钟点。若周期时间落入春季跳时的空缺时段，则该期顺延一个跳时间隔，下一期恢复原钟点；秋季重复时段只生成一次，使用第一次出现的时间。手动输入不存在或重复的当地时间时，表单会要求重新选择。任务时间始终按实际经过的小时数计算，例如 24 小时不会因夏令时变化而缩短。

已有工单升级时使用所属仓库的时区，不改变已保存的生成时间或周期结束时间。升级不会自动纠正过去误按 UTC 录入的时间；需要在后台核对并调整来源工单的开始日期。调整来源工单时区会重新解释表单内的当地时间并重算后续生成时间，不追溯修改已生成的历史工单。

本地使用 `manage.py runserver` 或 `scripts/run-dev.ps1` 启动时，网页进程自动启动周期扫描，每 30 秒执行一次，启动时立即补齐漏掉的期次。无需额外启动 Redis，也不依赖有人打开工作台。

每个周期都会生成一张独立工单，包括任务快照、负责人、任务时间和通知。首张工单完成或关闭后仍继续生成；取消工单或取消勾选“周期有效”后停止。生成时间不超过“周期结束时间”（包含恰好等于结束时间的期次）。停机后会按原计划时间补齐所有漏期，因此补出的历史工单可能已经逾期。

周期工单标题显示固定期次：首张为“第 1 期”，后续生成的工单依次为“第 2 期”“第 3 期”。期次独立保存，删除已生成的某一期不会让后续期次重新编号。工作台、工单、设备记录、后台和导出报表同步显示，标记随界面语言切换。

单次手动扫描：

```powershell
.\.venv\Scripts\python.exe manage.py generate_recurring_workorders
```

使用 WSGI/ASGI 部署时，另行保持以下调度进程运行：

```powershell
.\.venv\Scripts\python.exe manage.py run_workorder_scheduler
```

也可使用 Redis、Celery Worker 和 Celery Beat：

```powershell
.\.venv\Scripts\celery.exe -A config worker -l INFO
.\.venv\Scripts\celery.exe -A config beat -l INFO
```

Beat 同样每 30 秒扫描一次。上述生产调度方式选择一种即可；本地使用外部调度时设置 `MMS_LOCAL_SCHEDULER=0`。后续工单使用“周期来源工单 + 开始生成时间”唯一约束，同一期次不会重复生成。

## 已停用功能清理

维保模板、模板任务和维保计划已从运行模型、页面、数据库表及系统权限中移除；工单不再保留 `source_plan`、`plan_due_at` 旧字段。`apps/maintenance` 只保留必要的历史迁移，确保旧数据库升级和全新安装都能正常执行。

用户、组和仓库角色的权限选择框只列出当前可管理条目的 `view` 和 `modify`。执行 `migrate` 时会把原 `add`、`change`、`delete` 的授权合并到 `modify` 后删除旧权限。批量导入、前台单台录入、任务照片、消息和报表仍在使用。

## Vercel + Supabase 部署

项目保留本地 SQLite 和本地媒体目录，同时已支持在 Vercel 使用 Supabase PostgreSQL、私有 Supabase Storage 和 Vercel Cron。生产环境缺少数据库、对象存储或调度密钥时会拒绝启动，避免将业务数据意外写入 Vercel 临时磁盘。

完整的账号配置、环境变量、数据库初始化、域名绑定和验收步骤见 [Vercel + Supabase 部署指南](docs/VERCEL_SUPABASE_DEPLOYMENT.md)。生产变量样例见 `.env.example`，不得把真实值提交到 Git。

## 验证

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
```

当前测试覆盖仓库数据隔离、设备导入、一次性/周期性工单、联动下拉框、角色与组权限、简单密码、三语切换、任务快照、通知接收人范围和周期生成幂等性。
