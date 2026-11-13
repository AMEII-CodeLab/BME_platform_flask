"""Seed a repeatable XLAB project-plaza dataset for local development."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402
from exts import db  # noqa: E402
from models import ShowcaseProject, UserModel  # noqa: E402

OWNER_ID = 130
PROJECTS = [
    {
        "source": "camp", "track": "competition", "project_status": "ongoing", "title": "智能输液安全监护系统",
        "summary": "面向病房输液场景的轻量监护终端，持续识别余量、滴速与异常状态。",
        "description": "团队将称重传感、滴速识别与床旁提醒整合进一套可快速部署的原型，重点验证低成本硬件在真实护理流程中的稳定性与告警可读性。",
        "tags": ["医工交叉", "嵌入式", "物联网"], "members": ["林知行", "陈嘉言", "周予安"],
        "links": [{"label": "项目记录", "url": "https://example.com/xlab/infusion-monitor"}], "view_count": 268, "days_ago": 3,
    },
    {
        "source": "camp", "track": "innovation", "project_status": "done", "title": "多模态康复评估镜",
        "summary": "通过姿态、表情与动作节律数据，为康复训练提供可回看的阶段评估。",
        "description": "项目以普通摄像头和边缘推理为基础，将训练动作拆解为连续指标，帮助治疗师快速比较不同周期的训练表现，并生成面向患者的反馈摘要。",
        "tags": ["计算机视觉", "康复工程", "AI"], "members": ["许言", "梁思远", "郭书宁"],
        "links": [{"label": "演示资料", "url": "https://example.com/xlab/rehab-mirror"}], "view_count": 412, "days_ago": 18,
    },
    {
        "source": "camp", "track": "lab", "project_status": "done", "title": "微流控细胞培养监测站",
        "summary": "为微流控培养实验提供温度、流速与显微图像的一体化记录工作台。",
        "description": "团队完成了芯片夹具、环境传感和定时成像模块的整合，并用统一时间轴保存实验条件变化，减少人工抄录与多设备对时成本。",
        "tags": ["微流控", "生物医学", "硬件"], "members": ["沈若彤", "方子航"],
        "links": [{"label": "设计归档", "url": "https://example.com/xlab/microfluidics"}], "view_count": 337, "days_ago": 31,
    },
    {
        "source": "community", "track": "course", "project_status": "ongoing", "title": "宿舍能耗可视化终端",
        "summary": "把宿舍用电变化转化为直观的实时图形，辅助发现异常和调整习惯。",
        "description": "项目通过安全隔离的数据采集端记录能耗趋势，在本地终端呈现分时对比、异常峰值和节能目标，让能源数据成为可理解、可行动的信息。",
        "tags": ["校园", "数据可视化", "物联网"], "members": ["罗雨薇", "邓嘉诚"],
        "links": [{"label": "开源仓库", "url": "https://example.com/xlab/energy-display"}], "view_count": 196, "days_ago": 7,
    },
    {
        "source": "community", "track": "personal", "project_status": "done", "title": "开源实验记录器",
        "summary": "为小型实验团队设计的结构化记录工具，支持时间线、附件和版本追踪。",
        "description": "从个人实验日志出发，逐步补齐模板复用、数据导出和协作者批注，让实验过程能够被复查、复现，也便于结项后形成可持续维护的数字档案。",
        "tags": ["开源", "Web", "科研工具"], "members": ["陈敏捷"],
        "links": [{"label": "项目主页", "url": "https://example.com/xlab/lab-notebook"}], "view_count": 521, "days_ago": 45,
    },
    {
        "source": "community", "track": "innovation", "project_status": "idea", "title": "无障碍教室声场地图",
        "summary": "探索教室不同位置的语音可懂度，为听障同学和扩声改造提供参考。",
        "description": "构想通过便携采样设备记录教室声压、混响和语音清晰度，形成可交互的空间地图，并尝试给出座位选择与设备布置建议。",
        "tags": ["无障碍", "信号处理", "校园"], "members": ["李明轩"],
        "links": [{"label": "研究笔记", "url": "https://example.com/xlab/classroom-audio"}], "view_count": 128, "days_ago": 1,
    },
]


def find_owner():
    owner = db.session.get(UserModel, OWNER_ID)
    if owner and (owner.status or "active") == "active":
        return owner
    return UserModel.query.filter_by(status="active", role="user").order_by(UserModel.id.asc()).first()


def seed():
    owner = find_owner()
    if not owner:
        raise RuntimeError("No active non-admin user is available to own showcase records.")

    removed = 0
    for project in ShowcaseProject.query.filter_by(owner_user_id=OWNER_ID).all():
        title = (project.title or "").strip()
        if title and set(title) == {"?"}:
            db.session.delete(project)
            removed += 1

    now = datetime.now().replace(microsecond=0)
    created = updated = 0
    for item in PROJECTS:
        project = ShowcaseProject.query.filter_by(title=item["title"]).first()
        if project is None:
            project = ShowcaseProject(title=item["title"], owner_user_id=owner.id)
            db.session.add(project)
            created += 1
        else:
            updated += 1

        project.source = item["source"]
        project.source_ref = None
        project.owner_user_id = owner.id
        project.summary = item["summary"]
        project.description = item["description"]
        project.cover = None
        project.images_json = None
        project.tags = json.dumps(item["tags"], ensure_ascii=False)
        project.track = item["track"]
        project.project_status = item["project_status"]
        project.status = "visible"
        project.members_json = json.dumps(item["members"], ensure_ascii=False)
        project.links_json = json.dumps(item["links"], ensure_ascii=False)
        project.archive_ref = None
        project.view_count = item["view_count"]
        project.created_at = now - timedelta(days=item["days_ago"] + 12)
        project.updated_at = now - timedelta(days=item["days_ago"])

    db.session.commit()
    titles = [item["title"] for item in PROJECTS]
    rows = ShowcaseProject.query.filter(ShowcaseProject.title.in_(titles)).order_by(ShowcaseProject.id.asc()).all()
    print(f"owner={owner.id} removed_broken={removed} created={created} updated={updated}")
    for project in rows:
        print(f"{project.id}\t{project.source}\t{project.project_status}\t{project.title}")


if __name__ == "__main__":
    with app.app_context():
        seed()
