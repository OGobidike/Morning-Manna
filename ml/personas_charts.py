"""Reader personas in pictures (Card 7.6). Each function returns a Plotly figure.

    habit_map   every grouped reader, by when they read and how much at weekends
    graded      for each true persona, which group its readers landed in
    clarity     how clearly a reader's type shows, by how much they've read

Each group is coloured like the persona it turned out to match, the dashboard's colours
(early risers blue, commuters orange, weekend readers green), so the same kind of reader
looks the same everywhere in the project. The colours come from the grade, after the groups
were found; the groups themselves never saw a persona.

Run it from the repo root to save each chart as a web page in ml/charts/:
    python ml/personas_charts.py
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine

import personas as p
from streak_risk_charts import GRID, INK, MUTED, tidy

PERSONA_COLOURS = {"early_riser": "#2a78d6", "commuter": "#eb6834", "weekend_reader": "#1baf7a"}
HOURS = list(range(300, 601, 60))  # 05:00 to 10:00, for the time axis


def _graded(result: p.Result, truth: pd.Series, half: int | None = None) -> pd.DataFrame:
    readers = result.readers[result.readers.source == "synthetic"]
    if half is not None:
        readers = readers[readers.half == half]
    return readers.assign(persona=truth[readers.user_key].values)


def _colours(result: p.Result, truth: pd.Series) -> dict[int, str]:
    graded = _graded(result, truth)
    return {g: PERSONA_COLOURS[persona]
            for g, persona in p.matches(graded.group.values, graded.persona).items()}


def habit_map(result: p.Result, truth: pd.Series) -> go.Figure:
    """Each dot is a reader; each big ring is a group's centre."""
    colours = _colours(result, truth)
    centres = p.describe(result.found)
    fig = go.Figure()
    for row in centres.itertuples():
        mine = result.readers[result.readers.group == row.group]
        fig.add_trace(
            go.Scatter(
                x=mine.weekday_minute,
                y=mine.weekend_share * 100,
                mode="markers",
                name=f"Group {row.group} · {len(mine):,} readers",
                marker={"size": 5, "color": colours[row.group], "opacity": 0.45,
                        "line": {"width": 0}},
                customdata=np.column_stack([[p.clock(m) for m in mine.weekday_minute],
                                            [p.clock(m) for m in mine.weekend_minute]]),
                hovertemplate=f"Group {row.group}<br>Weekdays %{{customdata[0]}}, weekends "
                "%{customdata[1]}<br>%{y:.0f}% of reads at weekends<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=centres.weekday_minute,
            y=centres.weekend_share * 100,
            mode="markers+text",
            name="Each group's centre",
            marker={"size": 22, "color": "white", "line": {"width": 2.5, "color": INK}},
            text=[str(g) for g in centres.group],
            textfont={"color": INK, "size": 13},
            hovertext=centres.label,
            hoverinfo="text",
        )
    )
    # Each group's label sits in a clear patch, with an arrow to its centre
    offsets = {1: (40, -120), 2: (250, 0), 3: (60, -110)}
    for row in centres.itertuples():
        ax, ay = offsets.get(row.group, (0, -90))
        fig.add_annotation(
            x=row.weekday_minute, y=row.weekend_share * 100,
            text=f"<b>Group {row.group}</b><br>" + row.label.replace(", ", "<br>"),
            showarrow=True, arrowhead=0, arrowwidth=1, arrowcolor=MUTED, ax=ax, ay=ay,
            font={"size": 11, "color": INK}, align="left",
            bgcolor="rgba(255,255,255,0.92)", bordercolor=GRID, borderpad=5,
        )
    fig.update_xaxes(title="Usual reading time on weekdays, on the reader's own clock",
                     tickvals=HOURS, ticktext=[p.clock(m) for m in HOURS], range=[270, 625])
    fig.update_yaxes(title="Share of their reads at weekends", ticksuffix="%", range=[0, 100])
    return tidy(
        fig,
        f"K-means found {result.found.k} kinds of reader, from their habits alone",
        "Each dot is a reader with at least 5 reading days. It never saw their persona: "
        "the colours come from the grade afterwards",
        height=560,
    )


def graded(result: p.Result, truth: pd.Series) -> go.Figure:
    """For each true persona, the share of its readers in each group: on the checking half."""
    colours = _colours(result, truth)
    check = _graded(result, truth, half=1)
    table = p.crosstab(check.group.values, check.persona)
    fig = go.Figure()
    for group in table.columns:
        shares = table[group] * 100
        fig.add_trace(
            go.Bar(
                y=[p.PERSONA_NAMES[persona] for persona in table.index],
                x=shares,
                orientation="h",
                name=f"Group {group}",
                marker={"color": colours[group], "line": {"color": "white", "width": 2}},
                text=[f"{v:.0f}%" if v >= 6 else "" for v in shares],
                textposition="inside",
                insidetextanchor="middle",
                textfont={"color": "white", "size": 13},
                hovertemplate=f"%{{y}} in group {group}: %{{x:.1f}}%<extra></extra>",
            )
        )
    fig.update_layout(barmode="stack", bargap=0.35)
    fig.update_xaxes(title="Share of that persona's readers", ticksuffix="%", range=[0, 100],
                     showgrid=False)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return tidy(
        fig,
        f"Graded on readers it never saw: ARI {result.check_grade:.2f}, where 1 is a perfect match",
        "The checking half of the pretend readers, by their true persona, and the group "
        "each one landed in",
        height=430,
    ).update_layout(legend={"traceorder": "normal", "y": -0.34})  # after tidy, which sets -0.2


def clarity(table: pd.DataFrame) -> go.Figure:
    """ARI by reading days. Below the line (5 reads), readers aren't grouped at all."""
    below = table.reads == p.BAND_NAMES[0]
    fig = go.Figure(
        go.Bar(
            x=table.reads,
            y=table.ari,
            marker={"color": ["#c9c7bf" if b else "#55534e" for b in below]},
            text=[f"{a:.2f}" for a in table.ari],
            textposition="outside",
            textfont={"color": INK},
            customdata=table.readers,
            hovertemplate="%{x} reading days: ARI %{y:.2f} "
            "(%{customdata:,} readers)<extra></extra>",
            width=0.55,
        )
    )
    fig.add_annotation(x=p.BAND_NAMES[0], y=float(table.ari.iloc[0]) + 0.13,
                       text="too few to group:<br>left out", showarrow=False,
                       font={"size": 11, "color": MUTED})
    fig.update_xaxes(title="Days the reader has read", showgrid=False)
    fig.update_yaxes(title="ARI against the true personas", range=[0, 1.1],
                     tickvals=[0, 0.25, 0.5, 0.75, 1], gridcolor=GRID)
    return tidy(
        fig,
        "The more someone reads, the clearer their type",
        "The checking half, by how much each reader has read. "
        f"Below {p.MIN_READS} days a habit is mostly noise, so those readers aren't grouped",
        height=440,
    )


def everything(engine) -> dict[str, go.Figure]:
    result = p.run(engine)
    truth = p.load_truth(engine)
    table = p.clarity(p.load_habits(engine), truth, result.found)
    return {
        "map": habit_map(result, truth),
        "graded": graded(result, truth),
        "clarity": clarity(table),
    }


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    repo = Path(__file__).resolve().parents[1]
    out = Path(__file__).with_name("charts")
    out.mkdir(exist_ok=True)
    for name, fig in everything(create_engine(url)).items():
        fig.write_html(out / f"personas-{name}.html", include_plotlyjs="cdn")
        print(out.relative_to(repo) / f"personas-{name}.html")
