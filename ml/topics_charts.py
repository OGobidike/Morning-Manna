"""Topic tags in pictures (Card 8.3). Each function returns a Plotly figure.

    leaderboard  the three taggers on four measures, against chance
    by_tag       each tag's first screen of verses: how many of the top 20 are right

They read ml/results/topics.csv and topics_by_tag.csv, so they need neither the model nor the
database. The three taggers keep their Okabe-Ito colours on both charts (orange, green, blue),
which readers with colour blindness can tell apart, and every mark carries its number.

Run it from the repo root, after python ml/topics.py:
    python ml/topics_charts.py
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

import topics
from streak_risk_charts import GRID, INK, tidy

RESULTS = Path(__file__).with_name("results")
COLOURS = {"keyword": "#e69f00", "zero_shot": "#009e73", "trained": "#0072b2"}
NAMES = {
    "keyword": "Keywords",
    "zero_shot": "Meaning, no training",
    "trained": "Meaning, trained on Nave's",
}
MEASURES = {
    "precision_at_20": "A topic's top 20 verses:<br>how many are right",
    "average_precision": "Every tagged verse ranked<br>high (average precision)",
    "top1": "A verse's best tag is right",
    "top3": "A right tag in its best 3",
}


def leaderboard(board: pd.DataFrame) -> go.Figure:
    board = board.set_index("method")
    rows = list(reversed(MEASURES))
    fig = go.Figure()
    for offset, method in zip((0.22, 0.0, -0.22), NAMES, strict=True):
        values = board.loc[method, rows]
        fig.add_trace(
            go.Scatter(
                x=values,
                y=[rows.index(m) + offset for m in rows],
                mode="markers+text",
                name=NAMES[method],
                marker={
                    "size": 12,
                    "color": COLOURS[method],
                    "line": {"width": 2, "color": "white"},
                },
                text=[f"{v}%" for v in values],
                textposition="middle right",
                textfont={"color": INK, "size": 12},
                hovertemplate=f"<b>{NAMES[method]}</b>: %{{x}}%<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=board.loc["chance", rows],
            y=list(range(len(rows))),
            mode="markers",
            name="Picked at random",
            marker={"symbol": "line-ns", "size": 26, "line": {"width": 3, "color": INK}},
            hovertemplate="Chance: %{x}%<extra></extra>",
        )
    )
    fig.update_yaxes(
        tickvals=list(range(len(rows))),
        ticktext=[MEASURES[m] for m in rows],
        showgrid=False,
        range=[-0.6, len(rows) - 0.4],
    )
    fig.update_xaxes(ticksuffix="%", range=[0, 70], gridcolor=GRID)
    return tidy(
        fig,
        "Trained on Nave's, meaning tags verses best on every measure",
        f"{board.tags.iloc[0]} tags, graded on whole books each tagger never saw (KJV). "
        "The black line is chance",
        height=500,
    ).update_layout(margin={"l": 230, "t": 110}, legend={"y": -0.18})


def by_tag(per_tag: pd.DataFrame, labels: dict[str, str]) -> go.Figure:
    wide = per_tag.pivot(index="tag", columns="method", values="precision_at_20")  # percents
    wide = wide.sort_values(["trained", "zero_shot"])
    names = [f"{labels[t]} · {v:.0f}%" for t, v in zip(wide.index, wide.trained, strict=True)]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=names,
            x=wide.trained,
            orientation="h",
            name=NAMES["trained"],
            marker={"color": COLOURS["trained"]},
            hovertemplate="<b>%{y}</b>: %{x:.0f}% of the top 20 right (trained)<extra></extra>",
        )
    )
    for method in ("zero_shot", "keyword"):
        fig.add_trace(
            go.Scatter(
                y=names,
                x=wide[method],
                mode="markers",
                name=NAMES[method],
                marker={
                    "size": 9,
                    "color": COLOURS[method],
                    "line": {"width": 1.5, "color": "white"},
                },
                hovertemplate=f"<b>%{{y}}</b>: %{{x:.0f}}% ({NAMES[method]})<extra></extra>",
            )
        )
    fig.update_xaxes(
        title="Of a topic's top 20 verses, how many Nave's lists",
        ticksuffix="%",
        range=[0, 105],
        gridcolor=GRID,
    )
    fig.update_yaxes(showgrid=False)
    fig.update_layout(bargap=0.3)
    best, worst = wide.index[-1], wide.index[0]
    return tidy(
        fig,
        f"{labels[best]}: {wide.trained[best]:.0f}% of the first screen right. "
        f"{labels[worst]}: {wide.trained[worst]:.0f}%",
        "Each topic's first screen of 20 verses, chosen by a tagger that never saw the book. "
        "A miss can still be a good verse Nave's doesn't list",
        height=900,
    ).update_layout(margin={"l": 170, "t": 110}, legend={"orientation": "h", "y": -0.08})


def everything(results: Path = RESULTS) -> dict[str, go.Figure]:
    tags = topics.load_tags()
    labels = dict(zip(tags.tag, tags.label, strict=True))
    return {
        "leaderboard": leaderboard(pd.read_csv(results / "topics.csv")),
        "by-tag": by_tag(pd.read_csv(results / "topics_by_tag.csv"), labels),
    }


if __name__ == "__main__":
    repo = Path(__file__).resolve().parents[1]
    out = Path(__file__).with_name("charts")
    out.mkdir(exist_ok=True)
    for name, fig in everything().items():
        fig.write_html(out / f"topics-{name}.html", include_plotlyjs="cdn")
        print(out.relative_to(repo) / f"topics-{name}.html")
