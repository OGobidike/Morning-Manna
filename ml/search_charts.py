"""Semantic search in pictures (Card 8.2). Each function returns a Plotly figure.

    leaderboard  each method's precision@5 on the KJV and the ASV, with how sure we can be
    questions    every question, every method: where meaning wins, and where nothing does

They read ml/results/search_by_question.csv, so they need neither the model nor the database.
The translations are Okabe-Ito blue and orange, which readers with colour blindness can tell
apart, and every dot carries its number.

Run it from the repo root, after python ml/search.py:
    python ml/search_charts.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import search
from streak_risk_charts import GRID, INK, MUTED, tidy

BY_QUESTION = Path(__file__).with_name("results") / "search_by_question.csv"
COLOURS = {"KJV": "#0072b2", "ASV": "#e69f00"}
SHOWN = ["bge", "minilm", "hybrid", "keyword"]  # bge_hnsw scored exactly what bge did
NAMES = {
    "bge": "Meaning: BGE",
    "minilm": "Meaning: MiniLM",
    "hybrid": "Hybrid: BGE + keyword",
    "keyword": "Keyword search",
}
# Precision@5 comes in fifths. None found is the page's own grey; then light to dark blue
STEPS = {0: "#f0efec", 20: "#b7d3f6", 40: "#6da7ec", 60: "#2a78d6", 80: "#1c5cab", 100: "#0d366b"}
BOOTSTRAPS = 10_000


def interval(values: np.ndarray, seed: int = 7) -> tuple[float, float]:
    """A 95% bootstrap interval for the mean: draw the questions again, with replacement, many
    times, and see how far the average moves. With 30 questions, it moves a lot."""
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(values), (BOOTSTRAPS, len(values)))
    means = values[draws].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def leaderboard(graded: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    rows = list(reversed(SHOWN))  # the best at the top
    above = {"KJV": (0.17, "top center"), "ASV": (-0.17, "bottom center")}  # labels clear of lines
    for translation in search.TRANSLATIONS:
        offset, place = above[translation]
        mine = graded[graded.translation == translation]
        means, lows, highs = [], [], []
        for method in rows:
            values = mine[mine.method == method].precision_at_5.to_numpy() * 100
            low, high = interval(values)
            means.append(values.mean())
            lows.append(values.mean() - low)
            highs.append(high - values.mean())
        fig.add_trace(
            go.Scatter(
                x=means,
                y=[rows.index(m) + offset for m in rows],
                mode="markers+text",
                name=translation,
                marker={
                    "size": 11,
                    "color": COLOURS[translation],
                    "line": {"width": 2, "color": "white"},
                },
                error_x={
                    "type": "data",
                    "array": highs,
                    "arrayminus": lows,
                    "color": COLOURS[translation],
                    "thickness": 2,
                    "width": 0,
                },
                text=[f"{m:.0f}%" for m in means],
                textposition=place,
                textfont={"color": INK, "size": 12},
                customdata=np.column_stack(
                    [[NAMES[m] for m in rows], np.array(means) - lows, np.array(means) + highs]
                ),
                hovertemplate=f"<b>%{{customdata[0]}}</b>, {translation}: %{{x:.0f}}% "
                "(95%: %{customdata[1]:.0f} to %{customdata[2]:.0f})<extra></extra>",
            )
        )
    fig.update_yaxes(
        tickvals=list(range(len(rows))),
        ticktext=[NAMES[m] for m in rows],
        showgrid=False,
        range=[-0.6, len(rows) - 0.4],
    )
    fig.update_xaxes(
        title="Share of the first five results that answer the question (precision@5)",
        ticksuffix="%",
        range=[0, 60],
        gridcolor=GRID,
    )
    board = graded.groupby(["translation", "method"]).precision_at_5.mean()
    times = [board[t, "bge"] / board[t, "keyword"] for t in search.TRANSLATIONS]
    low, high = round(min(times)), round(max(times))
    return tidy(
        fig,
        f"Searching by meaning finds {low if low == high else f'{low} to {high}'} times what "
        "keywords find",
        f"{graded.question.nunique()} questions, their answers written before any search ran. "
        "Lines: where the average could fall<br>with other questions (95%). BGE through "
        "Postgres's index scored exactly what BGE did",
        height=540,
    ).update_layout(legend={"title": {"text": "Translation"}}, margin={"t": 125})


def questions(graded: pd.DataFrame, translation: str = "KJV") -> go.Figure:
    """A grid: one row per question, one column per method, each cell its precision@5."""
    mine = graded[graded.translation == translation]
    grid = mine.pivot(index="question", columns="method", values="precision_at_5")[SHOWN] * 100
    grid = grid.round().astype(int).sort_values(["bge", "minilm"], ascending=True)
    values = grid.to_numpy()
    steps = sorted(STEPS)
    scale = []
    for n, step in enumerate(steps):  # one flat band of colour per fifth
        scale += [[n / len(steps), STEPS[step]], [(n + 1) / len(steps), STEPS[step]]]
    fig = go.Figure(
        go.Heatmap(
            z=values,
            x=[NAMES[m] for m in SHOWN],
            y=grid.index,
            zmin=-10,
            zmax=110,
            colorscale=scale,
            showscale=False,
            xgap=2,
            ygap=2,
            hovertemplate="<b>%{y}</b><br>%{x}: %{z}% of the first five<extra></extra>",
        )
    )
    for row, question in enumerate(grid.index):
        for column, method in enumerate(SHOWN):
            value = int(values[row, column])
            fig.add_annotation(
                x=NAMES[method],
                y=question,
                text=f"{value}%",
                showarrow=False,
                font={
                    "size": 11,
                    "color": "white" if value >= 60 else (MUTED if value == 0 else INK),
                },
            )
    fig.update_xaxes(side="top", showgrid=False)
    fig.update_yaxes(showgrid=False)
    every = (values > 0).any(axis=1)
    return tidy(
        fig,
        f"Meaning wins on most questions; {int((~every).sum())} stump every method",
        f"Each question's precision@5 on the {translation}, BGE's best at the top. "
        "A 0 can still be good verses the answer key doesn't list",
        height=1020,
    ).update_layout(margin={"l": 290, "t": 135})


def everything(path: Path = BY_QUESTION) -> dict[str, go.Figure]:
    graded = pd.read_csv(path)
    return {"leaderboard": leaderboard(graded), "questions": questions(graded)}


if __name__ == "__main__":
    repo = Path(__file__).resolve().parents[1]
    out = Path(__file__).with_name("charts")
    out.mkdir(exist_ok=True)
    for name, fig in everything().items():
        fig.write_html(out / f"search-{name}.html", include_plotlyjs="cdn")
        print(out.relative_to(repo) / f"search-{name}.html")
