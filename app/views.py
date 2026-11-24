"""화면 블루프린트."""
from flask import Blueprint, render_template

bp = Blueprint("views", __name__)


@bp.get("/")
def index():
    return render_template("index.html")
