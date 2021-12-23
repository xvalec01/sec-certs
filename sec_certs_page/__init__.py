import os
from datetime import datetime
from pathlib import Path

import sentry_sdk
from celery import Celery, Task
from flag import flag
from flask import Flask, abort, jsonify, render_template, request
from flask_assets import Environment as Assets
from flask_breadcrumbs import Breadcrumbs, register_breadcrumb
from flask_caching import Cache
from flask_cors import CORS
from flask_login import LoginManager
from flask_mail import Mail
from flask_principal import Permission, Principal, RoleNeed
from flask_pymongo import PyMongo
from flask_redis import FlaskRedis
from flask_wtf import CSRFProtect
from sec_certs.config.configuration import config as tool_config
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import ignore_logger
from sentry_sdk.integrations.redis import RedisIntegration
from werkzeug.exceptions import HTTPException

app = Flask(__name__, instance_relative_config=True)
app.config.from_pyfile("config.py", silent=True)
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True
app.jinja_env.cache = {}
app.jinja_env.autoescape = True

if os.environ.get("TESTING", False):
    app.testing = True

if not app.testing:  # pragma: no cover
    sentry_sdk.init(
        dsn=app.config["SENTRY_INGEST"],
        integrations=[FlaskIntegration(), CeleryIntegration(), RedisIntegration()],
        environment=app.env,
        sample_rate=app.config["SENTRY_ERROR_SAMPLE_RATE"],
        traces_sample_rate=app.config["SENTRY_TRACES_SAMPLE_RATE"],
    )

    ignore_logger("sec_certs.helpers")
    ignore_logger("sec_certs.dataset.dataset")
    ignore_logger("sec_certs.sample.certificate")

tool_config.load(Path(app.instance_path) / app.config["TOOL_SETTINGS_PATH"])

mongo = PyMongo(app)


def make_celery(app):
    class ContextTask(Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    res = Celery(
        app.import_name,
        backend=app.config["CELERY_RESULT_BACKEND"],
        broker=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
        task_cls=ContextTask,
        timezone="Europe/Bratislava",
    )
    return res


login = LoginManager(app)
login.login_view = "admin.login"

principal = Principal(app)

celery = make_celery(app)

redis = FlaskRedis(app)

assets = Assets(app)

# debug = DebugToolbarExtension(app)

cache = Cache(app)

cors = CORS(app, origins="")

csrf = CSRFProtect(app)

mail = Mail(app)

breadcrumbs = Breadcrumbs(app)


@app.before_request
def set_sentry_user():
    try:
        sentry_sdk.set_user({"ip_address": request.remote_addr})
    except Exception:
        pass


@app.template_global("country_to_flag")
def to_flag(code):
    """Turn a country code to an emoji flag."""
    if code == "UK":
        code = "GB"
    return flag(code)


@app.template_global("blueprint_url_prefix")
def blueprint_prefix():
    """The url_prefix of the current blueprint."""
    return app.blueprints[request.blueprint].url_prefix


@app.template_filter("strptime")
def filter_strptime(dt, format):
    return datetime.strptime(dt, format) if dt else None


@app.template_filter("strftime")
def filter_strftime(dt_obj, format):
    if isinstance(dt_obj, datetime):
        return dt_obj.strftime(format)
    raise TypeError("Not a datetime")


@app.template_global("is_admin")
def is_admin():
    return Permission(RoleNeed("admin")).can()


from .admin import admin
from .cc import cc
from .fips import fips
from .notifications import notifications
from .pp import pp

app.register_blueprint(admin)
app.register_blueprint(cc)
app.register_blueprint(fips)
app.register_blueprint(notifications)
app.register_blueprint(pp)


@app.route("/")
@register_breadcrumb(app, ".", "Home")
def index():
    return render_template("index.html.jinja2")


@app.route("/feedback/", methods=["POST"])
def feedback():
    """Collect feedback from users."""
    data = request.json
    if set(data.keys()) != {"element", "comment", "path"}:
        return abort(400)
    for key in ("element", "comment", "path"):
        # TODO Add validation to client (or info abut feedback length).
        if not isinstance(data[key], str) or len(data[key]) > 256:
            return abort(400)
    # TODO add captcha
    data["ip"] = request.remote_addr
    data["timestamp"] = datetime.now()
    data["useragent"] = request.user_agent.string
    mongo.db.feedback.insert_one(data)
    return jsonify({"status": "OK"})


@app.route("/about/")
@register_breadcrumb(app, ".about", "About")
def about():
    return render_template("about.html.jinja2")


@app.errorhandler(HTTPException)
def error(e):
    return (
        render_template(
            "error.html.jinja2", code=e.code, name=e.name, description=e.description
        ),
        e.code,
    )
