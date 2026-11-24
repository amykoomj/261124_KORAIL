"""앱 팩토리. `flask --app app run` 또는 `python run.py`로 실행한다."""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from . import db
from .config import BASE_DIR, Config

ERROR_MESSAGES = {
    400: "요청이 올바르지 않습니다.",
    404: "요청한 페이지나 데이터를 찾을 수 없습니다.",
    405: "허용되지 않는 요청 방식입니다.",
    413: "파일이 너무 큽니다. 1MB 이하만 올릴 수 있습니다.",
    500: "서버에서 오류가 났습니다. 잠시 후 다시 시도하세요.",
}


def _setup_logging(app):
    if app.config.get("LOG_TO_STDOUT"):
        handler = logging.StreamHandler(sys.stdout)
    else:
        os.makedirs(app.config["LOG_DIR"], exist_ok=True)
        handler = RotatingFileHandler(
            os.path.join(app.config["LOG_DIR"], "app.log"),
            maxBytes=1_000_000, backupCount=5, encoding="utf-8",
        )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    for name in ("sales.audit", app.logger.name):
        lg = logging.getLogger(name)
        for h in list(lg.handlers):  # create_app을 여러 번 호출해도 핸들러가 쌓이지 않게
            if getattr(h, "_sales_handler", False):
                lg.removeHandler(h)
                h.close()
        handler._sales_handler = True
        lg.addHandler(handler)
        lg.setLevel(logging.INFO)


def _register_errors(app):
    @app.errorhandler(HTTPException)
    def http_error(e):
        msg = ERROR_MESSAGES.get(e.code, e.description)
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": msg}), e.code
        return render_template("error.html", code=e.code, message=msg), e.code

    @app.errorhandler(Exception)
    def server_error(e):
        app.logger.exception("처리되지 않은 오류: %s %s", request.method, request.path)
        msg = ERROR_MESSAGES[500]
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": msg}), 500
        return render_template("error.html", code=500, message=msg), 500


def create_app(test_config=None):
    app = Flask(__name__, instance_path=os.path.join(BASE_DIR, "instance"))
    app.config.from_object(Config)  # config.py가 import 시 .env를 읽음
    if test_config:
        app.config.update(test_config)
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    _setup_logging(app)
    db.init_app(app)
    db.ensure_db(app)  # DB 파일이 없으면 테이블 자동 생성

    from . import api, views
    app.register_blueprint(views.bp)
    app.register_blueprint(api.bp)
    _register_errors(app)
    return app
