"""为本地人才库推荐功能补充有区分度的候选人（幂等）。"""
from datetime import datetime

from app import create_app
from common.candidate_identity import identity_update
from common.db import col, insert_doc


CANDIDATES = [
    {
        "name": "顾晨曦", "gender": "女", "phone": "13988001001",
        "email": "ai.backend.guxi@example.com", "city": "杭州", "age": 29,
        "highest_education": "硕士", "major": "计算机科学与技术",
        "tags": "Python,Flask,MongoDB,大模型,LLM,RAG,向量数据库,电商,推荐系统,Docker,微服务",
        "school": "浙江大学", "company": "云鲸智能电商科技有限公司",
        "start": "2021-03", "end": "至今",
        "desc": "负责 AI 电商推荐平台与 RAG 智能客服，使用 Python、Flask、MongoDB 和向量数据库；接口 QPS 提升 65%。",
    },
    {
        "name": "程一帆", "gender": "男", "phone": "13988001002",
        "email": "java.backend.cheng@example.com", "city": "上海", "age": 31,
        "highest_education": "本科", "major": "软件工程",
        "tags": "Java,Spring Boot,MySQL,Redis,Kafka,微服务,Kubernetes,SaaS,订单,支付,库存",
        "school": "同济大学", "company": "星链企业服务有限公司",
        "start": "2019-07", "end": "至今",
        "desc": "负责 SaaS 订单与支付系统，采用 Java、Spring Boot、Redis、Kafka 和 Kubernetes，年度可用性 99.95%。",
    },
    {
        "name": "沈若琳", "gender": "女", "phone": "13988001003",
        "email": "frontend.shen@example.com", "city": "深圳", "age": 27,
        "highest_education": "本科", "major": "数字媒体技术",
        "tags": "React,TypeScript,Vite,Ant Design,前端,数据可视化,电商,商家后台,性能优化",
        "school": "深圳大学", "company": "橙子跨境电商有限公司",
        "start": "2022-06", "end": "至今",
        "desc": "建设跨境电商商家后台，使用 React、TypeScript、Vite 和 Ant Design，首屏时间降低 40%。",
    },
    {
        "name": "陆嘉禾", "gender": "男", "phone": "13988001004",
        "email": "ai.engineer.lu@example.com", "city": "北京", "age": 28,
        "highest_education": "硕士", "major": "人工智能",
        "tags": "Python,PyTorch,大模型,LLM,Agent,Prompt,Embedding,LangChain,RAG,模型微调,智能推荐",
        "school": "北京航空航天大学", "company": "灵境人工智能有限公司",
        "start": "2022-01", "end": "至今",
        "desc": "落地大模型 Agent 与智能推荐应用，负责模型微调、Embedding 检索及 RAG 评测，准确率提升 18%。",
    },
    {
        "name": "唐可欣", "gender": "女", "phone": "13988001005",
        "email": "ecommerce.ops.tang@example.com", "city": "广州", "age": 28,
        "highest_education": "本科", "major": "电子商务",
        "tags": "电商运营,用户增长,活动运营,商家运营,数据分析,GMV,转化率,复购率,ROI,A/B测试",
        "school": "暨南大学", "company": "悦选直播电商有限公司",
        "start": "2020-08", "end": "至今",
        "desc": "负责直播电商增长与活动运营，通过 A/B 测试将转化率提升 22%，年度 GMV 增长 45%。",
    },
    {
        "name": "魏思源", "gender": "男", "phone": "13988001006",
        "email": "product.wei@example.com", "city": "杭州", "age": 30,
        "highest_education": "本科", "major": "信息管理与信息系统",
        "tags": "产品经理,需求分析,产品规划,原型,用户研究,数据分析,AI应用,智能客服,电商,SaaS",
        "school": "杭州电子科技大学", "company": "数智商家服务有限公司",
        "start": "2019-04", "end": "至今",
        "desc": "负责 AI 商家服务产品规划及需求分析，推动智能客服上线，服务 2 万家商户，咨询转人工率下降 30%。",
    },
    {
        "name": "周景明", "gender": "男", "phone": "13988001007",
        "email": "sales.zhou@example.com", "city": "深圳", "age": 33,
        "highest_education": "本科", "major": "市场营销",
        "tags": "大客户,KA,企业服务,SaaS,AI,电商,客户开发,需求挖掘,解决方案,商务谈判,签约,回款,CRM,客户资源",
        "school": "中南财经政法大学", "company": "启航云科技有限公司",
        "start": "2018-03", "end": "至今",
        "desc": "面向品牌商家销售 AI SaaS 解决方案，年度签约额 1800 万元，重点客户续费率 92%。",
    },
    {
        "name": "许曼宁", "gender": "女", "phone": "13988001008",
        "email": "bd.xu@example.com", "city": "上海", "age": 29,
        "highest_education": "本科", "major": "国际经济与贸易",
        "tags": "BD,商务拓展,渠道合作,MCN,达人,直播电商,品牌客户,商务谈判,合同,渠道资源",
        "school": "上海对外经贸大学", "company": "潮流内容科技有限公司",
        "start": "2020-05", "end": "至今",
        "desc": "拓展 MCN、达人及品牌客户，建立 120 家渠道合作关系，单年促成合同额 900 万元。",
    },
    {
        "name": "林诗雨", "gender": "女", "phone": "13988001009",
        "email": "content.lin@example.com", "city": "厦门", "age": 26,
        "highest_education": "本科", "major": "新闻传播学",
        "tags": "内容运营,图文运营,视频运营,SEO,用户增长,数据运营,小红书,抖音,电商",
        "school": "厦门大学", "company": "海风品牌管理有限公司",
        "start": "2022-07", "end": "至今",
        "desc": "负责品牌图文、短视频和 SEO 内容矩阵，账号粉丝增长 35 万，电商引流转化率提升 16%。",
    },
    {
        "name": "韩子墨", "gender": "男", "phone": "13988001010",
        "email": "junior.general.han@example.com", "city": "武汉", "age": 24,
        "highest_education": "本科", "major": "工商管理",
        "tags": "沟通协作,Excel,客户服务,活动执行",
        "school": "湖北大学", "company": "江城商贸有限公司",
        "start": "2024-07", "end": "至今",
        "desc": "协助活动执行和客户资料维护，负责基础数据整理与跨部门沟通。",
    },
    {
        "name": "马天宇", "gender": "男", "phone": "13988001011",
        "email": "hardware.ma@example.com", "city": "东莞", "age": 32,
        "highest_education": "大专", "major": "机电一体化",
        "tags": "机械设计,CAD,设备维护,生产管理,质量控制",
        "school": "广东机电职业技术学院", "company": "精工自动化设备有限公司",
        "start": "2017-03", "end": "至今",
        "desc": "负责自动化设备结构设计、CAD 出图和生产现场质量控制。",
    },
    {
        "name": "苏晴", "gender": "女", "phone": "13988001012",
        "email": "hr.intern.su@example.com", "city": "广州", "age": 22,
        "highest_education": "本科", "major": "人力资源管理",
        "tags": "招聘,简历筛选,候选人沟通,面试安排,Excel,校园招聘,HR实习",
        "school": "华南师范大学", "company": "未来人才服务有限公司",
        "start": "2026-03", "end": "2026-09",
        "desc": "实习期间协助简历筛选、面试安排和校园招聘数据整理，累计支持 200 人次面试。",
    },
]


def seed() -> tuple[int, int]:
    now = datetime.now()
    created = 0
    updated = 0
    for spec in CANDIDATES:
        education = [{
            "school": spec["school"], "major": spec["major"],
            "degree": spec["highest_education"], "graduate_at": "2020-06",
        }]
        work_experience = [{
            "company": spec["company"], "position": spec["tags"].split(",", 1)[0],
            "start": spec["start"], "end": spec["end"], "desc": spec["desc"],
        }]
        doc = {
            key: value for key, value in spec.items()
            if key not in {"school", "company", "start", "end", "desc"}
        }
        doc.update({
            "education": education, "work_experience": work_experience,
            "source": "AI推荐测试", "remark": "人才库智能推荐测试候选人",
            "owner_id": "hr-001", "owner_name": "张薇", "version": 1,
            "updated_at": now,
        })
        identity_fields, unset_fields = identity_update(doc["phone"], doc["email"])
        doc.update(identity_fields)
        existing = col("candidates").find_one({"email": doc["email"]})
        if existing:
            update = {"$set": doc}
            if unset_fields:
                update["$unset"] = unset_fields
            col("candidates").update_one({"_id": existing["_id"]}, update)
            updated += 1
        else:
            doc["created_at"] = now
            insert_doc("candidates", doc)
            created += 1
    return created, updated


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        created_count, updated_count = seed()
        total = col("candidates").count_documents({"source": "AI推荐测试"})
        print(f"AI recommendation candidates: created={created_count}, updated={updated_count}, total={total}")
