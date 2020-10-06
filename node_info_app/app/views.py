from flask import redirect, url_for

from app import app
from .consts import METADATA_API_URI
from .helpers import get_categories_list, get_meta_data


@app.route('/')
def index():
    return redirect(url_for('info'))


@app.route("/info", methods=["GET"])
def info():
    """Method to get MetaData info"""
    categories = get_categories_list(METADATA_API_URI)
    return get_meta_data(categories)
