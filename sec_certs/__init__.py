import os

from flag import flag
from flask import Flask, render_template
from flask_debugtoolbar import DebugToolbarExtension

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_pyfile("config.py", silent=True)
    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    DebugToolbarExtension(app)

    @app.template_global("country_to_flag")
    def to_flag(code):
        return flag(code)

    with app.app_context():
        from .cc import cc
        app.register_blueprint(cc)
        from .pp import pp
        app.register_blueprint(pp)
        from .fips import fips
        app.register_blueprint(fips)

    @app.route("/")
    def index():
        return render_template("index.html.jinja2")

    return app
