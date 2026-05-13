"""页面占位：返回服务概览（M1.5 仅用作端到端联通验证）。"""
from __future__ import annotations

from flask import Blueprint, g, jsonify
from sqlalchemy import func, select

from database import models

bp = Blueprint("pages", __name__)


@bp.get("/")
def index():
    papers_count = g.db.execute(select(func.count(models.Paper.id))).scalar() or 0
    edges_count = g.db.execute(select(func.count(models.Edge.id))).scalar() or 0
    tasks_running = g.db.execute(
        select(func.count(models.Task.id)).where(models.Task.status == "running")
    ).scalar() or 0
    return jsonify({
        "service": "KnowledgeBase",
        "papers": papers_count,
        "edges": edges_count,
        "tasks_running": tasks_running,
    })
