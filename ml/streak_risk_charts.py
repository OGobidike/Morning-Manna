"""The streak-at-risk models in pictures (Card 7.2). Each function returns a Plotly figure.

    races      ROC curves: every model against the truth, the best any model could do
    budget     the nudge budget: nudge the riskiest share of readers, catch how many misses?
    honesty    calibration against the truth: when the model says 40%, is it really 40%?
    learned    what XGBoost and LightGBM leaned on, side by side

Colours follow the model's family, so they never clash with the dashboard's personas or the
A/B test's groups: the two tree models are red (bright and solid for XGBoost, dark and dashed
for LightGBM), logistic regression mid grey, the streak rule light grey and dotted, and the
truth ink, as everywhere in this project. Every line is also named in words.

Run it from the repo root to save each chart as a web page in ml/charts/:
    python ml/streak_risk_charts.py
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from sklearn.metrics import roc_curve
from sqlalchemy import create_engine

import streak_risk as sr

INK, MUTED, GRID, CARD = "#1a1a1a", "#55534e", "#ece9e1", "#ffffff"
FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
STYLE = {
    "streak_rule": {"color": "#c9c7bf", "dash": "dot", "width": 2},
    "logistic_regression": {"color": "#8a8983", "dash": "solid", "width": 2},
    "xgboost": {"color": "#e34948", "dash": "solid", "width": 2.5},
    "lightgbm": {"color": "#8f1d22", "dash": "dash", "width": 2.5},
    "truth": {"color": INK, "dash": "solid", "width": 3},
}
FEATURE_NAMES = {
    "streak_days": "Streak length",
    "read_rate_7d": "Read rate, last 7 days",
    "read_rate_28d": "Read rate, last 28 days",
    "read_time_spread_14d": "How much reading time wanders",
    "days_since_signup": "Days since joining",
    "tomorrow_weekday": "Tomorrow's weekday",
    "wording_b": "Reminder wording B",
}


def tidy(fig: go.Figure, title: str, subtitle: str, height: int = 460) -> go.Figure:
    """The project's quiet frame: a title that says what to see, a line on how to read it."""
    fig.update_layout(
        title={
            "text": f"<b>{title}</b><br><span style='font-size:13px;color:{MUTED}'>"
            f"{subtitle}</span>",
            "x": 0,
            "xanchor": "left",
        },
        font={"family": FONT, "color": INK, "size": 13},
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        height=height,
        margin={"l": 20, "r": 30, "t": 90, "b": 60},
        legend={"orientation": "h", "y": -0.2, "x": 0},
        hoverlabel={"font": {"family": FONT}},
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    return fig


def _chances(trained: list[sr.Trained], test: pd.DataFrame) -> dict[str, np.ndarray]:
    """Every model's chances for the held-out nights, then the truth's."""
    chances = {t.name: sr.miss_chance(t.model, test) for t in trained}
    chances["truth"] = test.true_miss_chance.to_numpy()
    return chances


def races(trained: list[sr.Trained], test: pd.DataFrame, board: pd.DataFrame) -> go.Figure:
    """ROC curves: how well each model ranks the nights that ended in a miss above the rest."""
    auc = board.set_index("model").roc_auc
    fig = go.Figure()
    fig.add_scatter(
        x=[0, 1], y=[0, 1], mode="lines", line={"color": GRID, "width": 1}, hoverinfo="skip",
        showlegend=False,
    )
    for name, chance in _chances(trained, test).items():
        false_alarm, caught, _ = roc_curve(test[sr.LABEL], chance)
        keep = np.linspace(0, len(caught) - 1, min(len(caught), 400)).astype(int)
        label = f"{sr.MODEL_NAMES[name]} · {auc[name]:.3f}"
        fig.add_scatter(
            x=false_alarm[keep], y=caught[keep], mode="lines", name=label,
            line=STYLE[name],
            hovertemplate=f"{sr.MODEL_NAMES[name]}<br>%{{y:.0%}} of misses caught, "
            "%{x:.0%} of the others flagged<extra></extra>",
        )
    fig.update_xaxes(title="Readers who read anyway, flagged by mistake", tickformat=".0%",
                     range=[0, 1])
    fig.update_yaxes(title="Readers who missed, flagged", tickformat=".0%", range=[0, 1.02])
    best = board[board.model.isin(["xgboost", "lightgbm"])].sort_values("roc_auc").iloc[-1]
    return tidy(
        fig,
        f"{sr.MODEL_NAMES[best.model]} gets {best.gap_closed:.0%} of the way from a simple rule "
        "to perfect knowledge",
        "ROC curves on the held-out weeks, with each model's area under the curve. "
        "The ink line is the truth, the best any model could do",
        height=520,
    )


def budget(trained: list[sr.Trained], test: pd.DataFrame, board: pd.DataFrame) -> go.Figure:
    """The nudge budget: nudge the riskiest share of streak nights, catch which share of misses."""
    missed = test[sr.LABEL].to_numpy()
    fig = go.Figure()
    fig.add_scatter(
        x=[0, 100], y=[0, 100], mode="lines", name="Nudging at random",
        line={"color": GRID, "width": 2}, hoverinfo="skip",
    )
    shares = np.arange(0, 101)
    for name, chance in _chances(trained, test).items():
        order = missed[np.argsort(-chance, kind="stable")]
        caught = np.concatenate([[0], np.cumsum(order) / order.sum() * 100])
        points = caught[np.round(shares / 100 * len(order)).astype(int)]
        fig.add_scatter(
            x=shares, y=points, mode="lines", name=sr.MODEL_NAMES[name], line=STYLE[name],
            hovertemplate=f"{sr.MODEL_NAMES[name]}: nudge %{{x}}% of readers, "
            "catch %{y:.0f}% of misses<extra></extra>",
        )
    share = sr.NUDGE_SHARE * 100
    fig.add_vline(x=share, line={"color": MUTED, "width": 1, "dash": "dot"},
                  annotation_text=f"the plan: nudge the riskiest {share:.0f}%",
                  annotation_position="top right", annotation_font={"color": MUTED, "size": 12})
    fig.update_xaxes(title="Share of streak nights nudged, riskiest first", ticksuffix="%",
                     range=[0, 100])
    fig.update_yaxes(title="Misses that got a nudge", ticksuffix="%", range=[0, 101])
    recall = board.set_index("model").nudge_recall
    best = recall[["xgboost", "lightgbm"]].idxmax()
    return tidy(
        fig,
        f"Nudging the riskiest {share:.0f}% catches {recall[best]:.0%} of tomorrow's misses; "
        f"the truth: {recall['truth']:.0%}",
        f"Each line ranks the held-out nights by its predicted risk and nudges from the top "
        f"({sr.MODEL_NAMES[best]} shown best)",
        height=500,
    )


def honesty(trained: list[sr.Trained], test: pd.DataFrame, name: str) -> go.Figure:
    """Calibration against the truth: the model's chances in ten groups, beside what was real."""
    model = next(t for t in trained if t.name == name)
    frame = pd.DataFrame(
        {
            "said": sr.miss_chance(model.model, test),
            "truth": test.true_miss_chance.to_numpy(),
            "missed": test[sr.LABEL].to_numpy(),
        }
    )
    frame["group"] = pd.qcut(frame.said, 10, labels=False, duplicates="drop")
    groups = frame.groupby("group").agg(
        said=("said", "mean"), truth=("truth", "mean"), missed=("missed", "mean"),
        nights=("said", "size"),
    )
    fig = go.Figure()
    fig.add_scatter(
        x=[0, 1], y=[0, 1], mode="lines", name="Perfectly honest",
        line={"color": GRID, "width": 2}, hoverinfo="skip",
    )
    fig.add_scatter(
        x=groups.said, y=groups.missed, mode="markers+lines", name="What happened",
        line={"color": STYLE[name]["color"], "width": 2},
        marker={"color": STYLE[name]["color"], "size": 10, "line": {"color": CARD, "width": 2}},
        customdata=groups.nights,
        hovertemplate="Said %{x:.0%}: %{y:.0%} missed (%{customdata:,} nights)<extra></extra>",
    )
    fig.add_scatter(
        x=groups.said, y=groups.truth, mode="markers", name="The truth",
        marker={"symbol": "diamond", "color": INK, "size": 10,
                "line": {"color": CARD, "width": 2}},
        hovertemplate="Said %{x:.0%}: the truth was %{y:.0%}<extra></extra>",
    )
    worst = round(float((groups.said - groups.truth).abs().max()) * 100, 1)
    edge = min(1.0, float(max(groups.said.max(), groups.truth.max(), groups.missed.max())) + 0.1)
    fig.update_xaxes(title=f"What {sr.MODEL_NAMES[name]} said: chance of a miss tomorrow",
                     tickformat=".0%", range=[0, edge])
    fig.update_yaxes(title="Share that missed, and the true chance", tickformat=".0%",
                     range=[0, edge])
    points = "point" if worst == 1.0 else "points"
    return tidy(
        fig,
        f"When {sr.MODEL_NAMES[name]} says a chance, it means it: never off the truth by more "
        f"than {worst} {points}",
        "Held-out nights in ten groups by predicted risk. Dots: what happened. "
        "Diamonds: the true chance",
        height=520,
    )


def learned(trained: list[sr.Trained]) -> go.Figure:
    """What the two tree models leaned on: each feature's share of their total gain."""
    trees = {t.name: sr.importance(t) for t in trained if t.name in ("xgboost", "lightgbm")}
    order = trees["lightgbm"].sort_values().index  # the smallest at the bottom
    fig = go.Figure()
    # Horizontal groups draw their first bar at the bottom, so LightGBM goes in first
    for name in ("lightgbm", "xgboost"):
        share = trees[name].reindex(order) * 100
        fig.add_bar(
            y=[FEATURE_NAMES[f] for f in order], x=share, orientation="h",
            name=sr.MODEL_NAMES[name],
            marker={"color": STYLE[name]["color"], "line": {"color": CARD, "width": 2}},
            text=[f"{v:.0f}%" for v in share], textposition="outside",
            textfont={"color": INK},
            hovertemplate=f"{sr.MODEL_NAMES[name]}: %{{y}}, %{{x:.1f}}% of the gain"
            "<extra></extra>",
        )
    tops = {name: share.index[0] for name, share in trees.items()}
    if tops["xgboost"] == tops["lightgbm"]:
        title = f"Both trees lean hardest on {FEATURE_NAMES[tops['xgboost']].lower()}"
    else:
        title = (f"XGBoost leans hardest on {FEATURE_NAMES[tops['xgboost']].lower()}, "
                 f"LightGBM on {FEATURE_NAMES[tops['lightgbm']].lower()}")
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08,
                      legend={"traceorder": "reversed"})
    fig.update_xaxes(title="Share of the model's total gain", ticksuffix="%",
                     range=[0, max(t.max() for t in trees.values()) * 118])
    fig.update_yaxes(gridcolor=CARD)
    return tidy(
        fig,
        title,
        "Each feature's share of the gain in each model: how much it improved the predictions",
        height=500,
    )


def everything(engine, answer_key: Path, tries: int = 25) -> dict[str, go.Figure]:
    board, trained, _, test = sr.run(engine, answer_key, tries)
    best = board[board.model.isin(["xgboost", "lightgbm"])].sort_values("roc_auc").model.iloc[-1]
    return {
        "races": races(trained, test, board),
        "budget": budget(trained, test, board),
        "honesty": honesty(trained, test, best),
        "learned": learned(trained),
    }


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    repo = Path(__file__).resolve().parents[1]
    out = Path(__file__).with_name("charts")
    out.mkdir(exist_ok=True)
    figures = everything(create_engine(url), repo / "data" / "answer_key" / "finish_chance.csv.gz")
    for name, fig in figures.items():
        fig.write_html(out / f"streak-risk-{name}.html", include_plotlyjs="cdn")
        print(out.relative_to(repo) / f"streak-risk-{name}.html")
