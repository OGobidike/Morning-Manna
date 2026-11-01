"""Morning Manna's reading dashboard: who reads, when, how steadily, and who comes back.

Run it after dbt build, from this folder:
    python app.py            then open http://localhost:8050

data.py asks the dbt marts the questions, charts.py draws the answers, and this file lays
out the page and wires up the persona filter.
"""

import os

import pandas as pd
from dash import Dash, Input, Output, dcc, html
from sqlalchemy import Engine, create_engine

import charts
import data

# What the filter redraws, in the order panels() returns them: the tiles, then six charts
PANELS = ["tiles", "who-reads", "clock", "rhythm", "finish", "streaks", "comes-back"]


def graph(figure, **props) -> dcc.Graph:
    """A chart that fills its card (the card's height is set in style.css) and resizes."""
    config = {"displayModeBar": False, **props.pop("config", {})}
    return dcc.Graph(
        figure=figure, responsive=True, config=config, style={"height": "100%"}, **props
    )


def change_badge(change: float | None, words: str, steady_below: float) -> html.Span:
    """▲ or ▼ with the change in words, so it never relies on colour alone. A change too
    small to matter says "steady" in grey rather than flashing red or green."""
    if change is None:
        return html.Span()
    if abs(change) < steady_below:
        return html.Span("● steady", className="change flat")
    up = change >= 0
    return html.Span(f"{'▲' if up else '▼'} {words}", className=f"change {'up' if up else 'down'}")


def tiles(numbers: dict, days, weeks, persona: str) -> list:
    """The four headline numbers, each with its week-on-week move and a 90-day sparkline."""

    def tile(label, value, badge, note, spark):
        return html.Div(
            [
                html.Div(label, className="label"),
                html.Div([html.Span(value, className="value"), badge], className="figure"),
                html.Div(note, className="note"),
                html.Div(graph(spark, config={"staticPlot": True}), className="spark"),
            ],
            className="tile",
        )

    def count(x):
        return "–" if x is None else f"{x:,.0f}"

    def percent(x):
        return "–" if x is None else f"{x:.1%}"

    new, daily, finish = numbers["new_readers"], numbers["daily_change"], numbers["finish_change"]
    # A rate resting on fewer than MIN_READERS readers is noise: the tile says so instead
    finish_ok = numbers["finish_readers"] >= charts.MIN_READERS
    day_7_ok = numbers["day_7_readers"] >= charts.MIN_READERS
    return [
        tile(
            "Readers",
            count(numbers["readers"]),
            change_badge(new, f"{count(new)} new this week", steady_below=1),
            "signed up so far",
            charts.sparkline(days.local_day, days.readers_so_far, persona),
        ),
        tile(
            "Read each day",
            count(numbers["daily_readers"]),
            change_badge(daily, "" if daily is None else f"{abs(daily):.0%}", steady_below=0.005),
            "7-day average, against the week before",
            charts.sparkline(days.local_day, days.active_readers, persona),
        ),
        tile(
            "Finish rate",
            percent(numbers["finish_rate"]) if finish_ok else "–",
            change_badge(
                finish if finish_ok else None,
                "" if finish is None else f"{abs(finish) * 100:.1f} pts",
                steady_below=0.001,
            ),
            "last 7 days, against the week before" if finish_ok else "too few readers yet",
            charts.sparkline(
                days.local_day,
                days.completion_7_day if finish_ok else None,
                persona,
                from_zero=False,
            ),
        ),
        tile(
            "Day-7 return",
            percent(numbers["day_7_return"]) if day_7_ok else "–",
            html.Span(),
            "came back a week after joining" if day_7_ok else "too few readers yet",
            charts.sparkline(
                weeks.cohort_week, weeks.day_7_rate if day_7_ok else None, persona, from_zero=False
            ),
        ),
    ]


def panels(engine: Engine, persona: str) -> tuple:
    """Everything the persona filter changes: the four tiles and the six charts."""
    rows = data.activity(engine, persona)
    days = data.daily_totals(rows)
    weeks = data.cohorts(engine, persona)
    return (
        tiles(data.headline(days, weeks), days, weeks, persona),
        charts.who_reads(rows, persona),
        charts.reading_clock(data.reading_times(engine, persona), persona),
        charts.reading_rhythm(days, persona),
        charts.finish_rate(days, persona),
        charts.streak_survival(data.streaks(engine, persona), persona),
        charts.who_comes_back(weeks, persona),
    )


def persona_pills(choices: list[str]) -> dcc.RadioItems:
    """The filter: one pill per persona that has readers, each with its colour dot."""
    return dcc.RadioItems(
        id="persona",
        value="all",
        inline=True,
        className="pills",
        options=[
            {
                "label": html.Span(
                    [
                        html.Span(className="dot", style={"background": charts.COLOURS[p]}),
                        data.PERSONAS[p],
                    ]
                ),
                "value": p,
            }
            for p in choices
        ],
    )


def card(panel: str, figure, size: str) -> html.Div:
    return html.Div(graph(figure, id=panel), className=f"card {size}")


def layout(engine: Engine) -> html.Main:
    """The page. Dash builds it again on every visit, so a refresh shows last night's data."""
    first = dict(zip(PANELS, panels(engine, "all")))
    through = data.daily_totals(data.activity(engine)).local_day.max()
    when = f"data through {through.day} {through:%B %Y}" if pd.notna(through) else "no data yet"
    return html.Main(
        [
            html.Header(
                [
                    html.H1(["📖 Morning Manna ", html.Span("Reading dashboard", className="tag")]),
                    html.P(
                        f"Pretend readers from ml/simulate.py, plus any real app users · {when}"
                        " · rebuilt by Airflow every night"
                    ),
                ]
            ),
            persona_pills(data.personas(engine)),
            html.Section(first["tiles"], id="tiles", className="tiles"),
            html.Section(
                [
                    card("who-reads", first["who-reads"], "wide"),
                    card("clock", first["clock"], "narrow"),
                    card("rhythm", first["rhythm"], "half"),
                    card("finish", first["finish"], "half"),
                    card("streaks", first["streaks"], "half tall"),
                    card("comes-back", first["comes-back"], "half tall"),
                ],
                className="grid",
            ),
            html.Footer(
                [
                    html.P(
                        f"Days, dots and signup weeks resting on fewer than {charts.MIN_READERS} "
                        "readers are left blank: with so few, one person swings the rate."
                    ),
                    html.P(
                        "Every number comes from the dbt marts in analytics/models/marts. The "
                        "readers are pretend, made by ml/simulate.py, so the patterns are the "
                        "habits it was told to give them. The dashboard is ready for real ones."
                    ),
                ]
            ),
        ]
    )


def create_app(engine: Engine) -> Dash:
    app = Dash(__name__, title="Morning Manna dashboard")
    app.layout = lambda: layout(engine)

    @app.callback(
        Output("tiles", "children"),
        *(Output(panel, "figure") for panel in PANELS[1:]),
        Input("persona", "value"),
        prevent_initial_call=True,  # the page already holds everyone's charts
    )
    def on_filter(persona):
        return panels(engine, persona)

    return app


if __name__ == "__main__":
    # The local docker database unless DATABASE_URL says otherwise
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    create_app(create_engine(url)).run(debug=True, port=8050)
