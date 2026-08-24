"""Flask 应用工厂（纯 MongoDB 数据栈，无 SQL 数据库）。"""
from flask import Flask
from flask_cors import CORS
from pymongo.errors import PyMongoError

from common.errors import register_error_handlers
from common.mongo import MongoUnavailable, init_mongo
from config import Config


def create_app(config_object=None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object or Config)
    app.json.ensure_ascii = False

    # 开发环境允许跨域（前端 5173 直连调试）；生产由 nginx 同源转发，无需跨域
    CORS(app, supports_credentials=True)

    register_error_handlers(app)

    # MongoDB（全部业务数据与文件元数据）与文件存储（OSS/本地兜底）
    init_mongo(app)
    with app.app_context():
        from common.candidate_identity import ensure_candidate_indexes
        from common.notifier import ensure_indexes as ensure_notification_indexes
        from modules.talent_pool_api import ensure_indexes as ensure_talent_pool_indexes

        ensure_candidate_indexes()
        ensure_notification_indexes()
        ensure_talent_pool_indexes()
    try:
        from common.storage import create_storage

        app.extensions["storage"] = create_storage(app)
    except Exception as e:
        # 生产环境：OSS 配置不完整直接阻止启动（禁止降级本地）；
        # 开发/测试环境：降级为无存储（仅影响文件接口），错误信息只含变量名不含密钥
        if app.config.get("ENV_NAME") == "production" and not app.config.get("TESTING"):
            raise
        app.logger.error("文件存储初始化失败: %s", e)
        app.extensions["storage"] = None

    # MongoDB 异常统一转 JSON 错误
    from flask import jsonify

    @app.errorhandler(MongoUnavailable)
    def handle_mongo_unavailable(e):
        return jsonify({"code": 5001, "msg": str(e) or "MongoDB 未连接", "data": None}), 200

    @app.errorhandler(PyMongoError)
    def handle_pymongo_error(e):
        app.logger.exception("MongoDB 操作异常")
        return jsonify({"code": 500, "msg": "数据库操作失败", "data": None}), 500

    from modules.auth import bp as auth_bp
    from modules.approval_api import bp as approval_bp
    from modules.audit_api import bp as audit_bp
    from modules.candidate_api import bp as candidate_bp
    from modules.dashboard_api import bp as dashboard_bp
    from modules.file_api import bp as file_bp
    from modules.health import bp as health_bp
    from modules.interview_api import bp as interview_bp
    from modules.job_api import bp as job_bp
    from modules.notification_api import bp as notification_bp
    from modules.onboarding_api import bp as onboarding_bp
    from modules.offer_api import bp as offer_bp
    from modules.job_api import public_bp as job_public_bp
    from modules.pipeline_api import bp as pipeline_bp
    from modules.platform_api import bp as platform_bp
    from modules.requirement_api import bp as requirement_bp
    from modules.report_api import bp as report_bp
    from modules.system_api import bp as system_bp
    from modules.talent_pool_api import bp as talent_pool_bp
    from modules.template_api import bp as template_bp
    from modules.tracking_stub import bp as tracking_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(requirement_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(job_bp)
    app.register_blueprint(job_public_bp)
    app.register_blueprint(interview_bp)
    app.register_blueprint(offer_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(candidate_bp)
    app.register_blueprint(approval_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(file_bp)
    app.register_blueprint(pipeline_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(platform_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(talent_pool_bp)
    app.register_blueprint(template_bp)
    app.register_blueprint(tracking_bp)

    with app.app_context():
        try:
            if app.config.get("SEED_DEMO_DATA"):
                from seed import seed_demo_data

                seed_demo_data()
        except MongoUnavailable:
            app.logger.error("MongoDB 不可用，跳过演示数据初始化（业务接口将返回 5001）")

    if not app.config.get("TESTING") and app.config.get("STAGE_RULE_WORKER_ENABLED", True):
        from common.stage_rules import start_stage_rule_worker

        start_stage_rule_worker(
            app, interval_seconds=app.config.get("STAGE_RULE_WORKER_INTERVAL", 60),
        )

    return app
