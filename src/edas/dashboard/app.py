from typing import Any, List, Dict

import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html, dash_table, Input, Output

# Import the database engine factory (Adapter)
from edas.db.connection import get_engine
# Import the analytics query functions (Application Logic)
from edas.dashboard import queries as Q
# Import the logging configuration
from edas.logging_config import setup_logging

# Suppress a specific mypy error often triggered by Dash callback argument types
# mypy: disable-error-code=arg-type

# Initialize logging for the dashboard application
setup_logging("INFO")


def _now_brussels_range() -> tuple[pd.Timestamp, pd.Timestamp]:
    """
    Calculates the default date range (last 10 days) ending at the current
    hour in the 'Europe/Brussels' timezone (as ENTSO-E data is often localized).
    """
    # Get current time in UTC (timezone-aware)
    now_utc = pd.Timestamp.utcnow()
    # Convert to the target European timezone
    now_bxl = now_utc.tz_convert("Europe/Brussels")
    # Floor to the current hour (e.g., 10:46 PM -> 10:00 PM)
    end = now_bxl.floor("h")
    # Set the start 10 days prior
    start = end - pd.Timedelta(days=10)
    # Return as standard datetime objects for the DatePickerRange
    return start.to_pydatetime(), end.to_pydatetime()


def _kpi_card(title: str, value_id: str) -> html.Div:
    """
    Component factory for creating a standardized Key Performance Indicator (KPI) card.
    
    Args:
        title: The static text to display as the KPI title.
        value_id: The Dash component ID used to update this KPI's value via callback.

    Returns:
        html.Div: A Dash HTML component representing the KPI card.
    """
    return html.Div(
        className="kpi-card",
        children=[
            html.Div(title, className="kpi-title"),
            # The value will be populated dynamically by the 'update_kpis' callback
            html.Div(id=value_id, className="kpi-value"),
        ],
    )


# Static options for the country selection dropdown
COUNTRY_OPTIONS: List[Dict[str, Any]] = [
    {"label": "France", "value": "FR"},
    {"label": "Germany", "value": "DE"},
]

# Create the database engine factory (using Dependency Injection pattern)
# This allows the query functions to get a connection from the pool.
engine_factory = get_engine

# Initialize the Dash application
app = Dash(__name__, title="Energy Analytics Dashboard")
# The 'server' variable is often needed for Gunicorn/WSGI deployment
server = app.server

# Define the main layout of the dashboard
app.layout = html.Div(
    [
        html.H1("Energy Analytics Dashboard"),

        # --- Section: User Controls (Filters) ---
        html.Div(
            [
                # Country Selector
                html.Div(
                    [
                        html.Label("Countries"),
                        dcc.Dropdown(
                            id="country-select",
                            options=COUNTRY_OPTIONS,
                            value=["FR"],  # Default value
                            multi=True,
                            style={"minWidth": 280},
                        ),
                    ]
                ),
                # Date Range Selector
                html.Div(
                    [
                        html.Label("Date Range"),
                        dcc.DatePickerRange(
                            id="date-range",
                            start_date=_now_brussels_range()[0],
                            end_date=_now_brussels_range()[1],
                            display_format="YYYY-MM-DD",
                        ),
                    ]
                ),
            ],
            style={
                "display": "flex",
                "gap": "16px",
                "flexWrap": "wrap",
                "alignItems": "flex-end",
                "marginBottom": "10px",
            },
        ),

        # --- Section: KPI Grid ---
        # This grid is updated by the 'update_kpis' callback
        html.Div(
            [
                _kpi_card("Total Consumption (MWh)", "kpi-total-cons"),
                _kpi_card("Total Production (MWh)", "kpi-total-prod"),
                _kpi_card("Net Balance (MW)", "kpi-net-balance"),
                _kpi_card("Avg Daily Cons. (MWh)", "kpi-avg-daily"),
                _kpi_card("Avg Weekly Cons. (MWh)", "kpi-avg-weekly"),
                _kpi_card("Avg Monthly Cons. (MWh)", "kpi-avg-monthly"),
            ],
            id="kpi-grid",
            style={
                "display": "grid",
                # Responsive grid, attempts 2 columns
                "gridTemplateColumns": "repeat(2, minmax(240px, 1fr))",
                "gap": "12px",
                "marginBottom": "16px",
            },
        ),

        # --- Section: Main Content Tabs ---
        dcc.Tabs(
            id="tabs",
            value="overview", # Default tab to show
            children=[
                dcc.Tab(label="Overview", value="overview"),
                dcc.Tab(label="Production Mix", value="mix"),
                dcc.Tab(label="Cross-Border Flows", value="flows"),
                dcc.Tab(label="Hourly Heatmap", value="heat"),
                dcc.Tab(label="Tables", value="tables"),
            ],
        ),
        # Content for the selected tab will be rendered here by 'render_tab' callback
        html.Div(id="tab-content", style={"marginTop": "14px"}),

        # --- Section: Inline CSS Styling ---
        # Using dcc.Markdown to inject custom CSS for styling KPI cards
        dcc.Markdown(
            """
<style>
.kpi-card {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 12px 16px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0,0,0,.04);
}
.kpi-title {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
}
.kpi-value {
  font-size: 22px;
  font-weight: 600;
}
/* Responsive grid for KPIs on larger screens */
@media (min-width: 920px) {
  #kpi-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
            """,
            dangerously_allow_html=True,
        ),
    ],
    # Main container style
    style={"maxWidth": "1200px", "margin": "0 auto", "fontFamily": "Inter, Segoe UI, Arial"},
)


# --- Callback: Persistent KPI Updater ---
@app.callback(
    Output("kpi-total-cons", "children"),
    Output("kpi-total-prod", "children"),
    Output("kpi-net-balance", "children"),
    Output("kpi-avg-daily", "children"),
    Output("kpi-avg-weekly", "children"),
    Output("kpi-avg-monthly", "children"),
    Input("country-select", "value"),
    Input("date-range", "start_date"),
    Input("date-range", "end_date"),
)
def update_kpis(countries, start_date, end_date):
    """
    This callback fires when filters change and updates all KPI cards.
    """
    # Ensure countries list is not empty (default to FR if none selected)
    countries = countries or ["FR"]
    # Fetch and process all KPI data from the queries module
    k = Q.kpis(engine_factory, countries, start_date, end_date)
    # Return formatted strings for each KPI card
    return (
        f"{k['total_consumption']:.0f}",
        f"{k['total_production']:.0f}",
        f"{k['net_balance']:.0f}",
        f"{k['avg_daily_consumption']:.0f}",
        f"{k['avg_weekly_consumption']:.0f}",
        f"{k['avg_monthly_consumption']:.0f}",
    )


# --- Callback: Main Tab Renderer (Charts/Tables) ---
@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "value"),
    Input("country-select", "value"),
    Input("date-range", "start_date"),
    Input("date-range", "end_date"),
)
def render_tab(tab, countries, start_date, end_date):
    """
    This callback fires when the selected tab or filters change.
    It renders the content (graphs or tables) for the currently active tab.
    """
    countries = countries or ["FR"]

    # --- Tab: Overview (Line Chart) ---
    if tab == "overview":
        df = Q.consumption_vs_production(engine_factory, countries, start_date, end_date)
        if df.empty:
            return html.Div("No data in this range.")
        fig = px.line(
            df,
            x="time_stamp",
            y=["consumption_mw", "production_mw"],
            labels={"value": "MW", "time_stamp": "Time", "variable": ""},
            title="Consumption vs Production",
        )
        return dcc.Graph(figure=fig)

    # --- Tab: Production Mix (Stacked Area Chart) ---
    if tab == "mix":
        df = Q.production_mix(engine_factory, countries, start_date, end_date)
        if df.empty:
            return html.Div("No data in this range.")
        fig = px.area(df, x="time_stamp", y="production_mw", color="source_type", title="Production Mix")
        return dcc.Graph(figure=fig)

    # --- Tab: Cross-Border Flows (Bar Chart) ---
    if tab == "flows":
        df = Q.crossborder_flows(engine_factory, countries, start_date, end_date)
        if df.empty:
            return html.Div("No flow data available.")
        # Aggregate total flow per direction for a cleaner bar chart
        agg = (
            df.groupby(["from_country_code", "to_country_code"], as_index=False)["flow_mw"]
            .sum()
            .sort_values("flow_mw", ascending=False)
        )
        fig = px.bar(
            agg,
            x="to_country_code",
            y="flow_mw",
            color="from_country_code",
            barmode="group",
            title="Net Flows by Country",
        )
        return dcc.Graph(figure=fig)

    # --- Tab: Hourly Heatmap ---
    if tab == "heat":
        df = Q.hourly_consumption(engine_factory, countries, start_date, end_date)
        if df.empty:
            return html.Div("No data in this range.")
        # Pivot data for heatmap (Day vs. Hour)
        pivot = df.pivot_table(index="day", columns="hour", values="consumption_mw", aggfunc="mean")
        # Ensure correct day of week order
        pivot = pivot.reindex(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
        fig = px.imshow(
            pivot,
            aspect="auto",
            labels=dict(x="Hour", y="Day", color="Consumption (MW)"),
            title="Hourly Consumption Patterns",
        )
        # FIX: Corrected typo dG -> dcc (Dash Core Components)
        return dcc.Graph(figure=fig)

    # --- Tab: Data Tables ---
    if tab == "tables":
        # Fetch data for both tables
        d1 = Q.daily_summary(engine_factory, countries, start_date, end_date)
        d2 = Q.flow_table(engine_factory, countries, start_date, end_date)
        return html.Div(
            [
                html.H4("Daily Consumption & Production"),
                dash_table.DataTable(
                    data=d1.to_dict("records"),
                    columns=[{"name": c, "id": c} for c in d1.columns],
                    page_size=10,
                    style_table={"overflowX": "auto"},
                ),
                html.Hr(),
                html.H4("Cross-Border Flows (Raw)"),
                dash_table.DataTable(
                    data=d2.to_dict("records"),
                    columns=[{"name": c, "id": c} for c in d2.columns],
                    page_size=10,
                    style_table={"overflowX": "auto"},
                ),
            ]
        )

    return html.Div("Unknown tab")


# Standard Python entry point to run the app in debug mode
if __name__ == "__main__":
    from edas.config import debug_enabled
    app.run(debug=debug_enabled())