"""业务状态机常量。"""

# 招聘需求（PRD v1.1）：草稿→待确认→招聘中→暂停→已完成→已关闭
REQ_DRAFT, REQ_PENDING_CONFIRM, REQ_RECRUITING, REQ_PAUSED, REQ_COMPLETED, REQ_CLOSED = (
    "draft", "pending_confirm", "recruiting", "paused", "completed", "closed",
)
REQUIREMENT_FLOW = {
    REQ_DRAFT: [REQ_PENDING_CONFIRM],
    REQ_PENDING_CONFIRM: [REQ_RECRUITING, REQ_CLOSED],
    REQ_RECRUITING: [REQ_PAUSED, REQ_COMPLETED, REQ_CLOSED],
    REQ_PAUSED: [REQ_RECRUITING, REQ_CLOSED],
    REQ_COMPLETED: [],
    REQ_CLOSED: [],
}

# 职位：草稿→待发布→招聘中→暂停招聘→已关闭
JOB_DRAFT, JOB_PENDING, JOB_RECRUITING, JOB_PAUSED, JOB_CLOSED = (
    "draft", "pending_publish", "recruiting", "paused", "closed",
)
JOB_FLOW = {
    JOB_DRAFT: [JOB_PENDING],
    JOB_PENDING: [JOB_RECRUITING, JOB_DRAFT],
    JOB_RECRUITING: [JOB_PAUSED, JOB_CLOSED],
    JOB_PAUSED: [JOB_RECRUITING, JOB_CLOSED],
    JOB_CLOSED: [],
}

# 应聘记录
APP_IN_PROGRESS, APP_ELIMINATED, APP_PENDING_ONBOARD, APP_ONBOARDED, APP_CLOSED = (
    "in_progress", "eliminated", "pending_onboard", "onboarded", "closed",
)
