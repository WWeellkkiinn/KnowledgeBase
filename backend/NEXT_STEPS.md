# Phase 1 遗留（4 个子代理汇总）

Phase 1 已并行落地 4 路代码，全 119 个后端 .py 文件编译通过。以下是子代理报上来的、需要 Phase 2 cutover 或后续迭代处理的事项。

## Agent A · Papers Domain
- `papers.Paper.journal_id` 当前是 `IntegerField` 而非 `ForeignKey(journals.Journal)`，避免 cross-app migration 依赖顺序问题。所有 app 一次性 migrate 完成后可改 FK。
- `citations` 与 `ai_analysis` app 无模型（zero-migration）。
- `papers.tasks.process_upload` 通过 `sys.path.insert` 懒导入旧 `services/pdf2md.py`。**Cutover 前必须把 Pdf2MdService 也搬到 `backend/`**，否则 Flask `services/` 一旦删除 worker 会断。

## Agent B · Discovery Domain
- `tracking/fetcher.py` 桥接式调用旧 `services/reference_fetcher.py`，且旧文件有 `functools.lru_cache` 但未 `import functools`。**Phase 2 整体迁过来时要把 import 修了**。
- `network/graph.py` 用 `apps.get_model("papers","Paper")` 跨 app 引用，依赖 Agent A 的 `papers` app 已 migrate。顺序：先 makemigrations papers，再 makemigrations network。
- `explore` 的 LLM 评分 `_score_batch` 留 TODO，等接 `ai_analysis.tasks.analyze_paper` 后再连。

## Agent C · Auth/Tenant/Admin
- 上线前确认 `SESAME_ONE_TIME=True` 的 token-invalidation 迁移（sesame 自带）已应用：`migrate sesame`。
- `admin_ext/templates/pending_users.html` 功能优先无 CSS 美化，正式公开前抛光。

## Agent D · Frontend
- `frontend/src/api/socket.ts`（owned-dir 外，未改）仍把 token 传给 Socket.IO auth。**SaaS 后后端的 socket 鉴权需改成 session cookie**。当前 `getToken()` 返回空串，HTTP 流程不受影响，但 Socket 实时进度推送会断。Phase 2 cutover 时需要：
  - 后端：socket 中间件改读 Django session
  - 前端：`socket.ts` 改用 `withCredentials` 而非 token

## 主代理合并后已处理
- `backend/config/settings.py`：INSTALLED_APPS 追加 11 个 app（含 sesame、admin_ext、django_celery_beat）+ CELERY_BEAT_SCHEDULE + DJANGO_SUPERADMIN_EMAIL / MAGIC_LINK_BASE_URL + CSRF_COOKIE_HTTPONLY=False + CSRF_TRUSTED_ORIGINS
- `backend/core/api.py`：挂载 7 个 ninja Router（auth / papers / citations(×2) / subscriptions / explore / network / tracking）
- `backend/requirements.txt`：追加 `django-celery-beat`
- `.env.example`：追加 DJANGO_SUPERADMIN_EMAIL / MAGIC_LINK_BASE_URL / DJANGO_CSRF_TRUSTED_ORIGINS

## 验收 Phase 1（下次 ECS 拉分支后执行）
```bash
docker compose up -d db redis
docker compose run --rm django python manage.py makemigrations
docker compose run --rm django python manage.py migrate
docker compose run --rm django python manage.py seed_journals
docker compose run --rm django pytest
docker compose up -d django celery
curl -fsS http://<host>:8000/api/health
```
