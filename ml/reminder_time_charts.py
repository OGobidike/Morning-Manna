"""The best reminder time in pictures (Card 7.7). Each function returns a Plotly figure.

    gaps        when each group starts reading after waking, and where its reminder goes
    graded      every contestant on the held-out weeks: on time, too early, or late
    learning    how fast a new reader's time is learned, read by read

The groups wear the colours of the persona each one turned out to match, like Card 7.6's
charts (early risers blue, commuters orange, weekend readers green); the colours come from
the grade, after the groups were found. The contestants are greys, the model red and the
truth ink, like the streak model's charts.

Run it from the repo root to save each chart as a web page in ml/charts/:
    python ml/reminder_time_charts.py
"""

import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import create_engine

import personas
import reminder_time as rt
from personas_charts import PERSONA_COLOURS
from streak_risk_charts import GRID, INK, MUTED, tidy

LATE, EARLY = "#e34948", "#d8d5cc"
BANDS = [-1, 0, 2, 4, 9, 10_000]
BAND_NAMES = ["none yet", "1–2", "3–4", "5–9", "10+"]
STYLE = {
    "wake": {"color": "#c9c7bf", "dash": "dot"},
    "own": {"color": "#8a8983", "dash": "solid"},
    "model": {"color": "#e34948", "dash": "solid"},
    "truth": {"color": INK, "dash": "solid"},
}


def _colours(engine) -> dict[int, str]:
    """Each group's colour: the persona most of its readers turned out to be."""
    groups = rt.load_groups(engine)
    truth = personas.load_truth(engine)
    both = groups.to_frame("group").join(truth, how="inner")
    return {
        g: PERSONA_COLOURS[p] for g, p in personas.matches(both.group.values, both.persona).items()
    }


def gaps(
    starts: pd.DataFrame, groups: pd.Series, profiles: rt.Profiles, colours: dict[int, str]
) -> go.Figure:
    """Each group's gaps after waking, with today's reminder (at waking) and the model's
    half-hour window."""
    learn = starts[(starts.local_day < rt.TEST_FROM) & (starts.source == rt.LEARN_FROM)]
    learn = learn.join(groups.rename("group"), on="user_key", how="inner")
    fig = make_subplots(
        rows=len(profiles.groups),
        cols=2,
        shared_xaxes=True,
        vertical_spacing=0.07,
        horizontal_spacing=0.05,
        column_titles=["<b>Weekdays</b>", "<b>Weekends</b>"],
    )
    for row, group in enumerate(profiles.groups, start=1):
        for col, weekend in ((1, False), (2, True)):
            mine = learn[(learn.group == group) & (learn.at_weekend == weekend)]
            pick = int(rt.GRID[profiles.curves[int(weekend), row - 1].argmax()])
            share = profiles.curves[int(weekend), row - 1].max()
            fig.add_trace(
                go.Histogram(
                    x=mine.minutes_after_wake,
                    xbins={"start": 0, "end": 240, "size": 5},
                    histnorm="percent",
                    marker={"color": colours[group], "line": {"color": "white", "width": 1}},
                    name=f"Group {group}",
                    showlegend=False,
                    hovertemplate=f"Group {group}: %{{y:.1f}}% of starts, %{{x}} min after "
                    "waking<extra></extra>",
                ),
                row=row,
                col=col,
            )
            # After the bars: plotly skips shapes on a subplot that has nothing in it yet
            fig.add_vrect(x0=pick, x1=pick + rt.WINDOW, fillcolor=INK, opacity=0.09,
                          line_width=0, layer="below", row=row, col=col)
            fig.add_vline(x=0, line={"color": INK, "width": 2, "dash": "dot"}, row=row, col=col)
            fig.add_annotation(
                x=pick + rt.WINDOW + 4,
                y=1,
                yref="y domain",
                xanchor="left",
                yanchor="top",
                text=f"remind at +{pick} min<br>on time {share:.0%}",
                showarrow=False,
                font={"size": 11, "color": INK},
                align="left",
                bgcolor="rgba(255,255,255,0.85)",
                row=row,
                col=col,
            )
        fig.update_yaxes(title=f"Group {group}", row=row, col=1)
    fig.update_yaxes(gridcolor=GRID, rangemode="tozero", ticksuffix="%")
    fig.update_xaxes(range=[-5, 200], tickvals=list(range(0, 181, 30)), gridcolor=GRID)
    fig.update_xaxes(title="Minutes after waking that they start reading", row=len(profiles.groups))
    fig.update_layout(bargap=0)
    return tidy(
        fig,
        "Commuters start over an hour after waking: a reminder at wake time is long gone",
        "Each group's reading starts on the learning weeks. Dotted: today's reminder, at wake "
        "time. Grey band: the half hour the model aims for",
        height=640,
    )


def graded(board: pd.DataFrame) -> go.Figure:
    """On time, too early and late, for every contestant on the held-out weeks."""
    fig = go.Figure()
    parts = (
        ("on_time", "On time: in the half hour before", INK),
        ("too_early", "Too early: over half an hour before", EARLY),
        ("late", "Late: after they'd started", LATE),
    )
    for column, name, colour in parts:
        share = board[column] * 100
        fig.add_trace(
            go.Bar(
                y=board.contestant,
                x=share,
                orientation="h",
                name=name,
                marker={"color": colour, "line": {"color": "white", "width": 2}},
                text=[f"{v:.0f}%" if v >= 6 else "" for v in share],
                textposition="inside",
                insidetextanchor="middle",
                textfont={"color": "white" if column != "too_early" else INK, "size": 13},
                hovertemplate=f"%{{y}}: {name.split(':')[0].lower()} %{{x:.1f}}%<extra></extra>",
            )
        )
    fig.update_layout(barmode="stack", bargap=0.35)
    fig.update_xaxes(
        title="Share of the held-out reading starts", ticksuffix="%", range=[0, 100], showgrid=False
    )
    fig.update_yaxes(autorange="reversed", showgrid=False)
    model = board.set_index("contestant").gap_closed[rt.CONTESTANTS["model"]]
    return tidy(
        fig,
        f"The model closes {model:.0%} of the gap between today's reminder and the best possible",
        "The three held-out weeks, replayed night by night: each pick uses only the reads "
        "before that morning",
        height=430,
    ).update_layout(legend={"traceorder": "normal", "y": -0.3})  # after tidy, which sets -0.2


def learning(graded_starts: pd.DataFrame) -> go.Figure:
    """On time by how many reads of that kind of day the reader had before that morning."""
    bands = pd.cut(graded_starts.reads_before, BANDS, labels=BAND_NAMES)
    fig = go.Figure()
    # The truth is drawn first and wide, so the model's line shows on top of it where they meet
    for name in ("truth", "wake", "own", "model"):
        style = STYLE[name]
        ahead = graded_starts.minutes_after_wake - graded_starts[name]
        on = ((ahead > 0) & (ahead <= rt.WINDOW)).groupby(bands, observed=True).mean() * 100
        fig.add_trace(
            go.Scatter(
                x=on.index.astype(str),
                y=on.values,
                mode="lines+markers",
                name=rt.CONTESTANTS[name],
                line={"color": style["color"], "dash": style["dash"],
                      "width": 6 if name == "truth" else 2.5},
                legendrank=list(STYLE).index(name),
                marker={"size": 9, "color": style["color"], "line": {"color": "white", "width": 2}},
                hovertemplate=f"{rt.CONTESTANTS[name]}<br>%{{x}} reads before: "
                "%{y:.1f}% on time<extra></extra>",
            )
        )
    fig.add_annotation(x=BAND_NAMES[2], y=57, ax=20, ay=-60, text="from the first read or two,"
                       "<br>the model's pick does as well<br>as the truth's", showarrow=True,
                       arrowhead=0, arrowwidth=1, arrowcolor=MUTED, align="left",
                       font={"size": 11, "color": INK}, bgcolor="rgba(255,255,255,0.92)")
    counts = bands.value_counts().reindex(BAND_NAMES)
    fig.update_xaxes(
        title="Reads on that kind of day before the morning",
        ticktext=[
            f"{b}<br><span style='font-size:11px;color:{MUTED}'>{n:,} starts</span>"
            for b, n in counts.items()
        ],
        tickvals=BAND_NAMES,
        showgrid=False,
    )
    fig.update_yaxes(title="On time", ticksuffix="%", range=[35, 80], gridcolor=GRID)
    return tidy(
        fig,
        "One or two reads are enough to place a new reader",
        "The held-out weeks, by how much the reader had read before each morning",
        height=460,
    ).update_layout(legend={"y": -0.32})


def everything(engine) -> dict[str, go.Figure]:
    result = rt.run(engine)
    starts = rt.load_starts(engine)
    groups = rt.load_groups(engine)
    profiles = rt.learn_profiles(starts, groups, rt.TEST_FROM)
    return {
        "gaps": gaps(starts, groups, profiles, _colours(engine)),
        "graded": graded(result.board),
        "learning": learning(result.graded),
    }


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    repo = Path(__file__).resolve().parents[1]
    out = Path(__file__).with_name("charts")
    out.mkdir(exist_ok=True)
    for name, fig in everything(create_engine(url)).items():
        fig.write_html(out / f"reminder-time-{name}.html", include_plotlyjs="cdn")
        print(out.relative_to(repo) / f"reminder-time-{name}.html")
