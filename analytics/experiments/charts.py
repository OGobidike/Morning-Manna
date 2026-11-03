"""The reminder experiment's pictures. Each function returns a Plotly figure.

Three charts, one question each, in the order the story goes:
    the_look    When did both groups have enough readers to look?
    the_result  How much did wording B change each measure, and where is the truth?
    the_drill   What does the analysis say across 1,200 practice runs?

Group A is green and group B magenta: two hues the dashboard doesn't use, so a colour never
means two things in this project. The pair passes the colour-blind checks; magenta is light
on white, so every mark also carries a label.

Run it from this folder after `dbt build` to save each chart as a web page in charts/
(the pictures in docs/images/experiment-*.png are screenshots of these pages):
    python charts.py
"""

import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine

import analyze
import drill

A, B = "#008300", "#e87ba4"  # group A green, group B magenta
NO_EFFECT = "#8a8983"  # the A/A runs: wording B no different
INK, MUTED, GRID, CARD = "#1a1a1a", "#55534e", "#ece9e1", "#ffffff"
FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"


def tidy(fig: go.Figure, title: str, subtitle: str, height: int = 420) -> go.Figure:
    """The same quiet frame as the dashboard: a title, a one-line way to read it, faint grids."""
    fig.update_layout(
        title={
            "text": f"<b>{title}</b><br><span style='font-size:13px;color:{MUTED}'>"
            f"{subtitle}</span>",
            "x": 0,
            "xanchor": "left",
            "y": 0.95,
        },
        font={"family": FONT, "color": INK, "size": 13},
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        height=height,
        margin={"l": 20, "r": 30, "t": 90, "b": 50},
        hoverlabel={"font": {"family": FONT}},
        legend={"orientation": "h", "y": -0.18, "x": 0},
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    return fig


def points(x: float) -> str:
    return f"{x * 100:+.1f}"


def the_result(results: dict[str, analyze.Comparison], truth: float) -> go.Figure:
    """B minus A for each measure, with its 95% interval, the guardrail floor and the truth.

    results: measure name -> comparison, decisive measure first.
    truth:   the planted effect on day-7 return, from the drill's twins.
    """
    names = list(results)[::-1]  # top to bottom, as given
    fig = go.Figure()
    # The guardrail floor and zero, behind everything
    fig.add_vline(x=0, line={"color": MUTED, "width": 1})
    fig.add_vline(
        x=-2,
        line={"color": MUTED, "width": 1, "dash": "dot"},
        annotation_text="guardrail floor: −2",
        annotation_position="top",
        annotation_font={"color": MUTED, "size": 12},
    )
    for name in names:
        c = results[name]
        fig.add_trace(
            go.Scatter(
                x=[c.difference * 100],
                y=[name],
                mode="markers+text",
                marker={"color": B, "size": 13, "line": {"color": CARD, "width": 2}},
                error_x={
                    "type": "data",
                    "symmetric": False,
                    "color": B,
                    "thickness": 2,
                    "width": 0,
                    "array": [(c.high - c.difference) * 100],
                    "arrayminus": [(c.difference - c.low) * 100],
                },
                text=[f"{points(c.difference)} points"],
                textposition="top center",
                textfont={"color": INK},
                hovertemplate=(
                    f"{name}<br>A {c.rate_a:.1%} · B {c.rate_b:.1%}<br>"
                    f"B minus A {points(c.difference)} points<br>"
                    f"95% interval {points(c.low)} to {points(c.high)}<br>"
                    f"p = {c.p_value:.3f}<extra></extra>"
                ),
                showlegend=False,
            )
        )
    day_7 = names[-1]
    fig.add_trace(
        go.Scatter(
            x=[truth * 100],
            y=[day_7],
            mode="markers+text",
            name="the truth",
            marker={
                "symbol": "diamond",
                "color": INK,
                "size": 11,
                "line": {"color": CARD, "width": 2},
            },
            text=[f"truth {points(truth)}"],
            textposition="bottom center",
            textfont={"color": INK},
            hovertemplate=f"The planted effect's true size: {points(truth)} points<extra></extra>",
            showlegend=False,
        )
    )
    # Room for the guardrail floor and the truth, and for any interval wider than usual
    left = min(-3.5, *(c.low * 100 - 0.5 for c in results.values()))
    right = max(10, truth * 100 + 1, *(c.high * 100 + 0.5 for c in results.values()))
    fig.update_xaxes(title="B minus A, in points", range=[left, right])
    fig.update_yaxes(gridcolor=CARD)
    c = results[day_7]
    inside = "sits inside" if c.low <= truth <= c.high else "falls outside"
    return tidy(
        fig,
        f"Wording B moved day-7 return {points(c.difference)} points; "
        f"the truth {inside} its interval",
        "Each dot is B minus A, with its 95% interval. The diamond is the planted truth",
    )


def the_look(readers: pd.DataFrame, per_group: int = analyze.PER_GROUP) -> go.Figure:
    """Readers who had reached day 7, by signup day, until both groups passed the planned size."""
    reached = readers[readers.can_have_day_7]
    counts = (
        reached.groupby(["signed_up_on", "reminder_variant"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=["A", "B"], fill_value=0)
        .sort_index()
        .cumsum()
    )
    _, look = analyze.at_the_look(readers, per_group)
    fig = go.Figure()
    fig.add_hline(
        y=per_group,
        line={"color": MUTED, "width": 1, "dash": "dot"},
        annotation_text=f"the planned size, {per_group:,} a group",
        annotation_position="top left",
        annotation_font={"color": MUTED, "size": 12},
    )
    if look is not None:
        fig.add_vline(x=pd.Timestamp(look), line={"color": INK, "width": 1})
        fig.add_annotation(
            x=pd.Timestamp(look),
            y=1,
            yref="paper",
            text=f"the one look, {look:%-d %b}",
            showarrow=False,
            xanchor="right",
            yanchor="top",
            xshift=-6,
            font={"color": INK, "size": 12},
        )
    for group, colour in (("A", A), ("B", B)):
        fig.add_trace(
            go.Scatter(
                x=pd.to_datetime(counts.index),
                y=counts[group],
                mode="lines",
                name=f"Group {group}",
                line={"color": colour, "width": 2},
                hovertemplate=f"Group {group}: %{{y:,}} readers by %{{x|%-d %b}}<extra></extra>",
            )
        )
        fig.add_annotation(
            x=pd.to_datetime(counts.index[-1]),
            y=counts[group].iloc[-1],
            text=f"{group}",
            showarrow=False,
            xanchor="left",
            xshift=6,
            font={"color": INK, "size": 13},
        )
    fig.update_xaxes(tickformat="%-d %b")
    fig.update_yaxes(tickformat=",")
    when = f"on {look:%-d %B}: the one look" if look is not None else "not yet"
    return tidy(
        fig,
        f"Both groups reached {per_group:,} readers {when}",
        "Readers who had reached their 7th day, counted by the day they joined",
    )


def the_drill(runs: pd.DataFrame, real: float, truth: float) -> go.Figure:
    """Every practice run's estimate: 1,000 with no effect, 200 with the planted one."""
    aa, ab = runs[runs.lift == 0], runs[runs.lift > 0]
    fig = go.Figure()
    bins = {"start": -8, "end": 14, "size": 0.5}
    for frame, colour, name in (
        (aa, NO_EFFECT, f"{len(aa):,} runs with no effect"),
        (ab, B, f"{len(ab):,} runs with wording B's effect"),
    ):
        fig.add_trace(
            go.Histogram(
                x=frame.estimate * 100,
                xbins=bins,
                name=name,
                histnorm="percent",
                marker={"color": colour, "line": {"color": CARD, "width": 1}},
                opacity=0.85,
                hovertemplate="%{y:.1f}% of runs estimated %{x} points<extra>" + name + "</extra>",
            )
        )
    for x, label, position in (
        (0, "no effect: 0", "top left"),
        (truth * 100, f"the truth: {points(truth)}", "top right"),
    ):
        fig.add_vline(
            x=x,
            line={"color": INK, "width": 1, "dash": "dot"},
            annotation_text=label,
            annotation_position=position,
            annotation_font={"color": INK, "size": 12},
        )
    fig.add_vline(
        x=real * 100,
        line={"color": INK, "width": 2},
        annotation_text=f"our run: {points(real)}",
        annotation_position="top left",
        annotation_font={"color": INK, "size": 12},
    )
    fig.update_layout(barmode="overlay", bargap=0.08)
    fig.update_xaxes(title="Estimated B minus A on day-7 return, in points")
    fig.update_yaxes(title=None, ticksuffix="%")
    return tidy(
        fig,
        "Across 1,200 practice runs, the analysis lands around the truth",
        "Share of each set's runs at each estimate, in half-point steps",
        height=440,
    )


def everything(engine) -> dict[str, go.Figure]:
    """All three charts, from the warehouse and the drill's record."""
    readers = analyze.readers_in_test(engine)
    counted, _ = analyze.at_the_look(readers)
    a, b = analyze.tally(counted, "A"), analyze.tally(counted, "B")
    results = {
        "🎯 Day-7 return": analyze.compare(a["day_7"], a["readers"], b["day_7"], b["readers"]),
        "🛡️ Day-1 return": analyze.compare(a["day_1"], a["readers"], b["day_1"], b["readers"]),
        "🛡️ Finish rate": analyze.compare(a["finished"], a["opened"], b["finished"], b["opened"]),
    }
    runs = pd.read_csv(Path(__file__).with_name("drill_runs.csv"))
    truth = drill.true_effect(runs[runs.lift == 0], runs[runs.lift > 0])
    real = results["🎯 Day-7 return"].difference
    return {
        "the-look": the_look(readers),
        "the-result": the_result(results, truth),
        "the-drill": the_drill(runs, real, truth),
    }


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    out = Path("charts")
    out.mkdir(exist_ok=True)
    for name, fig in everything(create_engine(url)).items():
        fig.write_html(out / f"{name}.html", include_plotlyjs="cdn")
        print(f"{out / name}.html")
