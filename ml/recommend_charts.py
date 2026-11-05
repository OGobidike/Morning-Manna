"""Because you read, in pictures (Card 8.4). Each function returns a Plotly figure.

    leaderboard  the five recommenders on three measures, against chance
    by_section   how many voted links the winner and shared words find, by the part of the
                 Bible read

They read ml/results/shelves.csv and shelves_by_section.csv, so they need neither the model nor
the database. Each recommender keeps its Okabe-Ito colour on both charts (the colours readers
with colour blindness can tell apart; words, meaning and topics match 8.3's), and every mark
carries its number.

Run it from the repo root, after python ml/recommend.py:
    python ml/recommend_charts.py
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from streak_risk_charts import GRID, INK, tidy

RESULTS = Path(__file__).with_name("results")
COLOURS = {
    "popular": "#999999",
    "words": "#e69f00",
    "meaning": "#009e73",
    "topics": "#cc79a7",
    "blend": "#0072b2",
}
NAMES = {
    "popular": "The most linked-to verses",
    "words": "Shared rare words",
    "meaning": "Nearest by meaning",
    "topics": "Similar topic tags",
    "blend": "Words, meaning and topics",
}
MEASURES = {
    "recall_at_10": "Of a verse's voted links,<br>how many are on its shelf",
    "hit_at_10": "The shelf has at least<br>one voted link",
    "precision_at_10": "Of the shelf's 10 verses,<br>how many are linked",
}


def leaderboard(board: pd.DataFrame) -> go.Figure:
    board = board.set_index("method")
    rows = list(reversed(MEASURES))
    offsets = dict(zip(NAMES, (0.28, 0.14, 0.0, -0.14, -0.28), strict=True))
    fig = go.Figure()
    for method, offset in offsets.items():
        values = board.loc[method, rows]
        fig.add_trace(
            go.Scatter(
                x=values,
                y=[rows.index(m) + offset for m in rows],
                mode="markers+text",
                name=NAMES[method],
                marker={
                    "size": 11,
                    "color": COLOURS[method],
                    "line": {"width": 2, "color": "white"},
                },
                text=[f"{v}%" for v in values],
                textposition="middle right",
                textfont={"color": INK, "size": 11},
                hovertemplate=f"<b>{NAMES[method]}</b>: %{{x}}%<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=board.loc["chance", rows],
            y=list(range(len(rows))),
            mode="markers",
            name="Picked at random",
            marker={"symbol": "line-ns", "size": 34, "line": {"width": 3, "color": INK}},
            hovertemplate="Chance: %{x}%<extra></extra>",
        )
    )
    fig.update_yaxes(
        tickvals=list(range(len(rows))),
        ticktext=[MEASURES[m] for m in rows],
        showgrid=False,
        range=[-0.5, len(rows) - 0.5],
    )
    top = board.drop("chance")[list(MEASURES)].to_numpy().max()
    fig.update_xaxes(ticksuffix="%", range=[0, top * 1.25 + 2], gridcolor=GRID)
    winner = board.index[board.winner.astype(bool)][0]
    return tidy(
        fig,
        f"{NAMES[winner]}: {board.loc[winner, 'recall_at_10']}% of a verse's voted links "
        "on a shelf of 10",
        f"{board.queries.iloc[0]:,} verses, graded on whole books each recommender never saw "
        "(KJV). The black line is chance",
        height=520,
    ).update_layout(margin={"l": 230, "t": 110}, legend={"y": -0.16, "orientation": "h"})


def by_section(sections: pd.DataFrame) -> go.Figure:
    """The record holds the winner and shared words only (the others moved under noise)."""
    wide = sections.pivot(index="section", columns="method", values="recall_at_10")
    best = wide.mean().idxmax()
    wide = wide.sort_values(best)
    queries = sections.drop_duplicates("section").set_index("section").queries
    names = [f"{s} · {queries[s]:,} verses" for s in wide.index]
    fig = go.Figure()
    for method in [m for m in NAMES if m in wide.columns]:
        fig.add_trace(
            go.Scatter(
                y=names,
                x=wide[method],
                mode="markers+text",
                name=NAMES[method],
                marker={
                    "size": 12 if method == best else 9,
                    "color": COLOURS[method],
                    "line": {"width": 1.5, "color": "white"},
                },
                text=[f"{v}%" for v in wide[method]],
                textposition="middle right" if method == best else "middle left",
                textfont={"color": INK, "size": 11},
                hovertemplate=f"<b>%{{y}}</b>: %{{x}}% ({NAMES[method]})<extra></extra>",
            )
        )
    fig.update_xaxes(
        title="Of a verse's voted links, how many are on its shelf of 10",
        ticksuffix="%",
        range=[0, wide.to_numpy().max() * 1.2 + 2],
        gridcolor=GRID,
    )
    fig.update_yaxes(showgrid=False)
    high, low = wide.index[-1], wide.index[0]
    return tidy(
        fig,
        f"Reading {high}: {wide.loc[high, best]}% of the links found. {low}: "
        f"{wide.loc[low, best]}%",
        "By the part of the Bible the reader just read, graded on books each recommender "
        "never saw. A miss can still be a good verse nobody linked",
        height=520,
    ).update_layout(margin={"l": 190, "t": 110}, legend={"orientation": "h", "y": -0.18})


def everything(results: Path = RESULTS) -> dict[str, go.Figure]:
    return {
        "leaderboard": leaderboard(pd.read_csv(results / "shelves.csv")),
        "by-section": by_section(pd.read_csv(results / "shelves_by_section.csv")),
    }


if __name__ == "__main__":
    repo = Path(__file__).resolve().parents[1]
    out = Path(__file__).with_name("charts")
    out.mkdir(exist_ok=True)
    for name, fig in everything().items():
        fig.write_html(out / f"shelves-{name}.html", include_plotlyjs="cdn")
        print(out.relative_to(repo) / f"shelves-{name}.html")
