# sec_certs_page/cc/dash.py
import dash
import plotly.express as px
from dash import dcc, html

from sec_certs_page.cc.dashboard import CCDashboard, CCDashboardConfig
from sec_certs_page.common.dashboard.registry import DashboardRegistry

from . import get_cc_analysis


def initialize_cc_dashboard() -> CCDashboard:
    registry = DashboardRegistry[CCDashboard, CCDashboardConfig]()
    registry.register_dashboard_type("cc_standard", CCDashboard)

    config: CCDashboardConfig = {
        "id": "cc-main",
        "title": "CC Certificates Dashboard",
        "refresh_interval": 30,
        "chart_types": ["pie", "bar"],
        "category_filters": ["EAL", "Protection Profile"],
    }

    return registry.create_dashboard("cc_standard", config)


dash.register_page(
    __name__,
    name="CC",
    path="/cc/",
    layout=lambda: html.Div(
        [
            html.H1("This is our CC page"),
            html.Div("This is our CC page content."),
            dcc.Graph(
                figure=px.pie(
                    get_cc_analysis()["categories"],
                    title="Certificates by category",
                    names="name",
                    values="value",
                    labels={"value": "count"},
                )
            ),
        ]
    ),
)
