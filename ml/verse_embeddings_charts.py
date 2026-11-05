"""Verse embeddings in pictures (Card 8.1). Each function returns a Plotly figure.

    chapter_map  every chapter laid out by meaning (t-SNE), coloured by the Bible's sections
    agreement    how often a verse's nearest neighbours share its section, against chance

The section colours are the Okabe-Ito palette, chosen so readers with colour blindness can tell
them apart, and every section is also named in the legend, with its count.

Run it from the repo root, after python ml/verse_embeddings.py:
    python ml/verse_embeddings_charts.py
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from sklearn.manifold import TSNE
from sqlalchemy import create_engine

import verse_embeddings as ve
from streak_risk_charts import GRID, INK, tidy

COLOURS = {
    "The Law": "#0072b2",
    "History": "#56b4e9",
    "Poetry and wisdom": "#009e73",
    "The prophets": "#e69f00",
    "Gospels and Acts": "#d55e00",
    "Letters": "#cc79a7",
    "Revelation": "#55534e",
}


def chapters(verses: pd.DataFrame, vectors: np.ndarray) -> tuple[pd.DataFrame, np.ndarray]:
    """One point per chapter: the average of its verses' vectors. A single verse is short and
    noisy; a chapter's average says what the chapter is about."""
    verses = verses.reset_index(drop=True)
    keys = verses.groupby(["book_order", "chapter"], sort=True).indices
    table = pd.DataFrame(
        [{"book_order": b, "chapter": c, "book": verses.book[rows[0]],
          "section": verses.section[rows[0]], "verses": len(rows)}
         for (b, c), rows in keys.items()]
    )
    means = np.vstack([vectors[rows].mean(axis=0) for rows in keys.values()])
    return table, means / np.linalg.norm(means, axis=1, keepdims=True)


def chapter_map(verses: pd.DataFrame, vectors: np.ndarray) -> go.Figure:
    """Every chapter, squeezed from 384 dimensions to 2 by t-SNE, which keeps close neighbours
    close. The model never saw the sections: the colours come afterwards."""
    table, means = chapters(verses, vectors)
    perplexity = min(30, max(5, len(table) // 4))
    xy = TSNE(2, perplexity=perplexity, init="pca", random_state=7).fit_transform(means)
    table = table.assign(x=xy[:, 0], y=xy[:, 1])
    fig = go.Figure()
    for name, colour in COLOURS.items():
        mine = table[table.section == name]
        if mine.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=mine.x, y=mine.y, mode="markers", name=f"{name} · {len(mine):,} chapters",
                marker={"size": 7, "color": colour, "opacity": 0.8,
                        "line": {"width": 0.5, "color": "white"}},
                text=[f"{b} {c}" for b, c in zip(mine.book, mine.chapter, strict=True)],
                hovertemplate="<b>%{text}</b><extra></extra>",
            )
        )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x")
    return tidy(
        fig,
        "Chapters that mean alike sit together, and the Bible's sections show",
        f"All {len(table):,} chapters, each the average of its verses, laid out by meaning "
        "alone (t-SNE). The colours came afterwards",
        height=640,
    )


def agreement(checked: pd.DataFrame) -> go.Figure:
    """For each section: the share of nearest neighbours from the same section, and chance."""
    table = checked[checked.section != "All"]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=table.section,
            x=table.same_section * 100,
            orientation="h",
            name="Nearest neighbours from the same section",
            marker={"color": [COLOURS[s] for s in table.section]},
            text=[f"{v:.0%}" for v in table.same_section],
            textposition="outside",
            textfont={"color": INK},
            hovertemplate="%{y}: %{x:.1f}% of neighbours from the same section<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            y=table.section,
            x=table.chance_section * 100,
            mode="markers",
            name="Picked at random (chance)",
            marker={"symbol": "line-ns", "size": 22, "line": {"width": 3, "color": INK}},
            hovertemplate="%{y}: %{x:.1f}% by chance<extra></extra>",
        )
    )
    every = checked[checked.section == "All"].iloc[0]
    fig.update_xaxes(
        title="Share of nearest neighbours", ticksuffix="%", range=[0, 105], gridcolor=GRID
    )
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_layout(bargap=0.35)
    return tidy(
        fig,
        f"A verse's nearest neighbours share its section {every.same_section:.0%} of the time, "
        f"against {every.chance_section:.0%} by chance",
        f"{ve.SAMPLE:,} KJV verses and their {ve.NEIGHBOURS} nearest neighbours in meaning. "
        "The black line is what picking verses at random would give",
        height=460,
    ).update_layout(legend={"y": -0.25})


def everything(engine) -> dict[str, go.Figure]:
    verses = ve.load_verses(engine)
    verses = verses[verses.translation == ve.CHECK_TRANSLATION].reset_index(drop=True)
    stored = ve.load_vectors(engine).set_index("verse_id").embedding
    vectors = np.vstack(stored[verses.verse_id].to_numpy())
    return {"map": chapter_map(verses, vectors), "agreement": agreement(ve.check(verses, vectors))}


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    repo = Path(__file__).resolve().parents[1]
    out = Path(__file__).with_name("charts")
    out.mkdir(exist_ok=True)
    for name, fig in everything(create_engine(url)).items():
        fig.write_html(out / f"verse-embeddings-{name}.html", include_plotlyjs="cdn")
        print(out.relative_to(repo) / f"verse-embeddings-{name}.html")
