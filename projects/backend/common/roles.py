"""角色常量（8 类流程参与角色）。"""

HR = "hr"
BUSINESS_SCREENER = "business_screener"
INTERVIEWER = "interviewer"
ORG_APPROVER = "org_approver"
GM = "gm"
CHAIRMAN = "chairman"
OFFER_SENDER = "offer_sender"
SSC = "ssc"

ALL_ROLES = [HR, BUSINESS_SCREENER, INTERVIEWER, ORG_APPROVER, GM, CHAIRMAN, OFFER_SENDER, SSC]

ROLE_NAMES = {
    HR: "HR",
    BUSINESS_SCREENER: "业务复筛人员",
    INTERVIEWER: "面试人员",
    ORG_APPROVER: "组织统筹审批人",
    GM: "总经理",
    CHAIRMAN: "董事长",
    OFFER_SENDER: "Offer发送专人",
    SSC: "SSC入职处理人员",
}
