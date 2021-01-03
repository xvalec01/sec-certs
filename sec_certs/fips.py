import json
from collections import namedtuple
from sys import getsizeof
from hashlib import blake2b

from flask import Blueprint, render_template, current_app, url_for
from flask_paginate import Pagination
from pkg_resources import resource_stream

from networkx import info as graph_info

from .utils import create_graph, send_json_attachment, entry_json_func, entry_graph_json_func, entry_func, network_graph_func

fips = Blueprint("fips", __name__, url_prefix="/fips")

fips_data = {}
fips_names = []
fips_graphs = []
fips_map = {}
fips_types = {}

FIPSEntry = namedtuple("FIPSEntry", ("id", "name", "hashid", "status", "level", "vendor", "type"))


@fips.before_app_first_request
def load_fips_data():
    global fips_names, fips_data, fips_graphs, fips_map, fips_types
    with current_app.open_instance_resource("fips.json") as f:
        loaded_fips_data = json.load(f)
    with resource_stream("sec_certs", "fips_types.json") as f:
        fips_types = json.load(f)
    print(" * (FIPS) Loaded types")
    fips_data = {blake2b(key.encode(), digest_size=10).hexdigest(): value for key, value in
                 loaded_fips_data["certs"].items()}
    fips_names = list(sorted(FIPSEntry(int(value["cert_id"]), value["module_name"], key, value["status"],
                                       value["level"], value["vendor"], value["type"]) for key, value in
                             fips_data.items()))
    print(" * (FIPS) Loaded certs")

    fips_references = {cert["cert_id"]: {
        "hashid": hashid,
        "name": cert["module_name"],
        "refs": cert["connections"],
        "href": url_for("fips.entry", hashid=hashid),
        "type": fips_types[cert["type"]]["id"] if cert["type"] in fips_types else ""
    } for hashid, cert in fips_data.items()}

    fips_graph, fips_graphs, fips_map = create_graph(fips_references)
    print(f" * (FIPS) Got {len(fips_data)} certificates")
    print(f" * (FIPS) Got {len(fips_references)} certificates with IDs")
    print(f" * (FIPS) Got graph:\n{graph_info(fips_graph)}")
    print(" * (FIPS) Made network")
    del fips_graph

    mem_taken = sum(map(getsizeof, (fips_names, fips_data, fips_graphs, fips_map, fips_types)))
    print(f" * (FIPS) Size in memory: {mem_taken}B")


@fips.app_template_global("get_fips_type")
def get_fips_type(name):
    return fips_types.get(name, None)


@fips.route("/types.json")
def types():
    return send_json_attachment(fips_types)


@fips.route("/")
@fips.route("/<int:page>/")
def index(page=1):
    per_page = current_app.config["SEARCH_ITEMS_PER_PAGE"]
    pagination = Pagination(page=page, per_page=per_page, total=len(fips_names), href=url_for(".index") + "{0}/",
                            css_framework="bootstrap4", alignment="center")
    return render_template("fips/index.html.jinja2", certs=fips_names[(page - 1) * per_page:page * per_page],
                           pagination=pagination, title=f"FIPS 140 ({page}) | seccerts.org")


@fips.route("/network/")
def network():
    return render_template("fips/network.html.jinja2", url=url_for(".network_graph"),
                           title="FIPS 140 network | seccerts.org")


@fips.route("/network/graph.json")
def network_graph():
    return network_graph_func(fips_graphs)


@fips.route("/search/")
def search():
    pass


@fips.route("/analysis/")
def analysis():
    return


@fips.route("/<string(length=20):hashid>/")
def entry(hashid):
    return entry_func(hashid, fips_data, "fips/entry.html.jinja2")


@fips.route("/<string(length=20):hashid>/graph.json")
def entry_graph_json(hashid):
    return entry_graph_json_func(hashid, fips_data, fips_map)


@fips.route("/<string(length=20):hashid>/cert.json")
def entry_json(hashid):
    return entry_json_func(hashid, fips_data)