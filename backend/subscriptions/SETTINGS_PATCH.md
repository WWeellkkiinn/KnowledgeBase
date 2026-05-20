# Settings Patch — Discovery Domain Apps (Agent B)

主代理合并清单。以下改动**不要直接修改**对应文件，由主代理统一合并。

---

## 1. `backend/config/settings.py` — INSTALLED_APPS

在 `"accounts"` 之后追加：

```python
    # Discovery domain (Agent B)
    "subscriptions",
    "explore",
    "network",
    "tracking",
```

---

## 2. `backend/config/settings.py` — CELERY_BEAT_SCHEDULE

在文件末尾（或 Celery 配置块内）追加：

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "nightly-fill-explore-pools": {
        "task": "subscriptions.tasks.nightly_fill_explore_pools",
        "schedule": crontab(hour=2, minute=0),   # 02:00 UTC
        "options": {"expires": 3600},
    },
    "nightly-track-refresh": {
        "task": "subscriptions.tasks.nightly_track_refresh",
        "schedule": crontab(hour=2, minute=30),  # 02:30 UTC
        "options": {"expires": 3600},
    },
}
```

---

## 3. `backend/core/api.py` — Router mounts

在 `api = NinjaAPI(...)` 定义之后、`health` 端点之前追加：

```python
from subscriptions.api import router as subscriptions_router
from explore.api import router as explore_router
from network.api import router as network_router
from tracking.api import router as tracking_router

api.add_router("/subscriptions", subscriptions_router, tags=["subscriptions"])
api.add_router("/explore", explore_router, tags=["explore"])
api.add_router("/network", network_router, tags=["network"])
api.add_router("", tracking_router, tags=["tracking"])  # /papers/{id}/forward-track etc.
```

---

## 4. `requirements.txt` — New dependencies

追加（如尚未存在）：

```
django-celery-beat>=2.6,<3
httpx>=0.27,<1
```

`django-celery-beat` 提供 Beat 调度持久化（数据库存储 schedule）。
`httpx` 供 `explore/services.py` 的 OpenAlex HTTP 调用使用。

如果使用 django-celery-beat，还需在 `INSTALLED_APPS` 追加：

```python
    "django_celery_beat",
```

---

## 5. Celery Beat 任务汇总

| Task name | 触发时间 (UTC) | 说明 |
|---|---|---|
| `subscriptions.tasks.nightly_fill_explore_pools` | 每天 02:00 | 为所有活跃订阅派发 `fill_pool_task` |
| `subscriptions.tasks.nightly_track_refresh` | 每天 02:30 | 调用 `tracking.tasks.refresh_core_papers_task` |

子任务（由以上任务 dispatch）：

| Sub-task | 触发方式 |
|---|---|
| `explore.tasks.fill_pool_task` | 由 `nightly_fill_explore_pools` 逐 sub_id 派发 |
| `tracking.tasks.forward_track_task` | 由 `refresh_core_papers_task` 逐 paper 派发 |
| `tracking.tasks.backward_track_task` | 由 `refresh_core_papers_task` 逐 paper 派发 |
| `subscriptions.tasks.generate_queries_task` | 创建/更新订阅 description 时即时触发 |
