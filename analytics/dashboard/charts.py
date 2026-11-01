"""The dashboard's pictures. Each function takes tables from data.py and returns a Plotly figure.

Colour follows the persona everywhere: choose Commuters and every chart turns commuter orange.
"All readers" is violet, a colour no persona uses, so a colour never means two things. The
persona colours are the first four slots of a palette checked for colour-blind safety.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import data

COLOURS = {
    "all": "#6250d6",
    "early_riser": "#2a78d6",
    "commuter": "#eb6834",
    "weekend_reader": "#1baf7a",
    "app": "#eda100",
}
INK, MUTED, GRID, CARD = "#1a1a1a", "#55534e", "#ece9e1", "#ffffff"
FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# A day, a dot or a cohort resting on fewer readers than this is left blank: with only a
# handful of readers one person swings the rate from 0% to 100%, and the colour would shout
# about noise
MIN_READERS = 20
DAY_TICKS = "%-d %b"  # 9 Aug: no year line under the first tick (it gets clipped)


# ---- Colour helpers ---------------------------------------------------------------------


def mix(colour: str, other: str, amount: float) -> str:
    """Blend two hex colours: amount 0 gives colour, 1 gives other."""
    a = [int(colour[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b))


def faded(colour: str, alpha: float) -> str:
    """A hex colour as see-through rgba, for fills under lines."""
    r, g, b = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def ramp(persona: str) -> list:
    """One hue for heat maps, light to dark: a whisper of the colour up to a deep shade of it."""
    colour = COLOURS[persona]
    return [[0, mix(colour, "#ffffff", 0.92)], [0.55, colour], [1, mix(colour, "#000000", 0.45)]]


# ---- The shared look --------------------------------------------------------------------


def tidy(fig: go.Figure, title: str, subtitle: str = "", legend: bool = False) -> go.Figure:
    """The same quiet frame for every chart: a title that says what it shows, a one-line
    subtitle that says how to read it, faint grids, and the legend below when there is one.

    No y-axis titles: the titles name what is counted, and a sideways title trips Plotly
    while a resizing chart is still measuring its card.
    """
    fig.update_layout(
        title=dict(
            text=f"<b>{title}</b>",
            subtitle=dict(text=subtitle, font=dict(size=12, color=MUTED)),
            x=0.01,
            xanchor="left",
            font=dict(size=16, color=INK),
        ),
        font=dict(family=FONT, size=12, color=MUTED),
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        margin=dict(l=8, r=8, t=78 if subtitle else 48, b=52 if legend else 8),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="top", y=-0.1, x=0, title=None),
        hoverlabel=dict(bgcolor="white", bordercolor=GRID, font=dict(family=FONT, color=INK)),
    )
    fig.update_xaxes(gridcolor=GRID, linecolor=GRID, zeroline=False, ticks="")
    fig.update_yaxes(gridcolor=GRID, linecolor=GRID, zeroline=False, ticks="")
    return fig


def nothing_yet(fig: go.Figure, message: str = "No readers here yet") -> go.Figure:
    """What an empty chart says instead of drawing blank axes."""
    fig.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(size=14, color=MUTED),
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def clock(half_hour: int) -> str:
    """Half hour 14 as "07:00"."""
    return f"{half_hour // 2:02d}:{30 * (half_hour % 2):02d}"


# ---- The six charts ---------------------------------------------------------------------


def who_reads(activity: pd.DataFrame, persona: str) -> go.Figure:
    """Readers who read each day: stacked by persona for everyone, one persona's own otherwise."""
    fig = go.Figure()
    if activity.empty:
        return nothing_yet(tidy(fig, "Who reads each day"))
    if persona == "all":
        wide = activity.pivot_table(
            index="local_day",
            columns="persona",
            values="active_readers",
            aggfunc="sum",
            fill_value=0,
        )
        order = [p for p in data.PERSONAS if p in wide.columns]
        for p in order:
            fig.add_scatter(
                x=wide.index,
                y=wide[p],
                name=data.PERSONAS[p],
                stackgroup="readers",
                mode="lines",
                line=dict(width=1.5, color="white"),
                fillcolor=COLOURS[p],
                hovertemplate=f"{data.PERSONAS[p]}: %{{y:,}}<extra></extra>",
            )
        # Name each band where it ends, if it's thick enough to hold the words
        last, base = wide.iloc[-1], 0
        total = last[order].sum()
        for p in order:
            if total and last[p] / total >= 0.08:
                fig.add_annotation(
                    x=wide.index[-1],
                    y=base + last[p] / 2,
                    text=f"{data.PERSONAS[p]} {last[p]:,}",
                    xanchor="right",
                    showarrow=False,
                    bgcolor="rgba(255,255,255,0.85)",
                    font=dict(size=11, color=INK),
                    borderpad=2,
                )
            base += last[p]
        subtitle = "Readers who finished a reading, by persona"
    else:
        days = data.daily_totals(activity)
        colour = COLOURS[persona]
        fig.add_scatter(
            x=days.local_day,
            y=days.active_readers,
            name="Each day",
            mode="lines",
            line=dict(width=1, color=colour),
            fill="tozeroy",
            fillcolor=faded(colour, 0.14),
            hovertemplate="Read that day: %{y:,}<extra></extra>",
        )
        fig.add_scatter(
            x=days.local_day,
            y=days.active_7_day_average,
            name="7-day average",
            mode="lines",
            line=dict(width=3, color=mix(colour, "#000000", 0.2)),
            hovertemplate="7-day average: %{y:,.0f}<extra></extra>",
        )
        subtitle = f"{data.PERSONAS[persona]} · bold line: the 7-day average"
    fig = tidy(fig, "Who reads each day", subtitle, legend=True)
    fig.update_layout(hovermode="x unified", legend_traceorder="normal")
    fig.update_xaxes(hoverformat="%a %-d %b %Y", tickformat=DAY_TICKS)
    fig.update_yaxes(rangemode="tozero", tickformat=",")
    if activity.groupby("local_day").active_readers.sum().max() < 10:
        fig.update_yaxes(dtick=1)  # a handful of readers: whole numbers only, no "2.5 readers"
    return fig


def reading_clock(times: pd.DataFrame, persona: str) -> go.Figure:
    """A 24-hour clock of when readings are finished, in each reader's own time zone."""
    grid = data.clock_grid(times)
    fig = go.Figure()
    if grid.to_numpy().sum() == 0:
        return nothing_yet(tidy(fig, "The reading clock"))
    theta = [slot * 7.5 + 3.75 for slot in range(48)]  # each half hour is 7.5° of the circle
    spans = [f"{clock(s)}–{clock(s + 1) if s < 47 else '24:00'}" for s in range(48)]
    for p in grid.columns:
        fig.add_barpolar(
            r=grid[p],
            theta=theta,
            width=[7.5] * 48,
            name=data.PERSONAS[p],
            customdata=spans,
            marker=dict(color=COLOURS[p], line=dict(color="white", width=1)),
            hovertemplate=f"%{{customdata}} · {data.PERSONAS[p]}: %{{r:,}} readings<extra></extra>",
        )
    busiest = int(grid.sum(axis=1).idxmax())
    fig.add_annotation(
        text=f"busiest<br><b>{clock(busiest)}</b>",
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(size=13, color=INK),
    )
    fig = tidy(
        fig,
        "The reading clock",
        "When readings finish, in readers' own time",
        legend=persona == "all",
    )
    fig.update_layout(
        polar=dict(
            barmode="stack",
            hole=0.3,
            bgcolor=CARD,
            angularaxis=dict(
                rotation=90,
                direction="clockwise",
                tickmode="array",
                tickvals=[hour * 15 for hour in range(0, 24, 3)],
                ticktext=[f"{hour:02d}:00" for hour in range(0, 24, 3)],
                gridcolor=GRID,
                linecolor=GRID,
                tickfont=dict(size=10),
            ),
            radialaxis=dict(showticklabels=False, ticks="", gridcolor=GRID, showline=False),
        ),
        margin_b=52 if persona == "all" else 28,
    )
    return fig


def reading_rhythm(days: pd.DataFrame, persona: str) -> go.Figure:
    """Each day's share of readers who read, laid out like a wall calendar."""
    fig = go.Figure()
    calendar = data.rhythm(days)
    if calendar.read_share.notna().sum() == 0:
        return nothing_yet(tidy(fig, "Reading rhythm"))

    def grid(column: str) -> pd.DataFrame:
        return calendar.pivot(index="weekday", columns="week", values=column).reindex(range(7))

    share, readers, joined, day = (
        grid(c) for c in ("read_share", "active_readers", "readers_so_far", "local_day")
    )
    share = share.where(joined >= MIN_READERS)
    if share.notna().sum().sum() == 0:
        return nothing_yet(tidy(fig, "Reading rhythm"), "Too few readers to show yet")
    hover = [
        [
            [f"{d:%a} {d.day} {d:%b}" if pd.notna(d) else "", r, j]
            for d, r, j in zip(day.iloc[w], readers.iloc[w], joined.iloc[w])
        ]
        for w in range(7)
    ]
    fig.add_heatmap(
        z=share.to_numpy(dtype=float),
        x=share.columns,
        y=WEEKDAYS,
        customdata=hover,
        colorscale=ramp(persona),
        # Colour spans the days' own range so the weekly rhythm shows; the colour bar
        # says what that range is (a colour, unlike a bar's length, needn't start at 0)
        zmin=float(np.nanmin(share.to_numpy(dtype=float))),
        zmax=float(np.nanmax(share.to_numpy(dtype=float))),
        xgap=3,
        ygap=3,
        hoverongaps=False,
        colorbar=dict(tickformat=".0%", thickness=8, outlinewidth=0, len=0.9),
        hovertemplate=(
            "%{customdata[0]}: <b>%{z:.0%}</b> read<br>%{customdata[1]:,} of %{customdata[2]:,} "
            "readers<extra></extra>"
        ),
    )
    fig = tidy(
        fig,
        "Reading rhythm",
        "Share of readers who read, day by day",
    )
    fig.update_xaxes(
        type="date",
        tickformat=DAY_TICKS,
        tick0=share.columns.min(),
        dtick=14 * 24 * 60 * 60 * 1000,  # every other Monday, in milliseconds
        showgrid=False,
    )
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return fig


def finish_rate(days: pd.DataFrame, persona: str) -> go.Figure:
    """Of readers who opened a reading, the share who finished one: each day, and over 7 days."""
    fig = go.Figure()
    if days.completion_rate.notna().sum() == 0:
        return nothing_yet(tidy(fig, "Finish rate"))
    colour = COLOURS[persona]
    daily = days.completion_rate.where(days.opened_reading >= MIN_READERS)
    weekly = days.completion_7_day.where(
        days.opened_reading.rolling(7, min_periods=7).sum() >= MIN_READERS
    )
    if daily.notna().sum() == 0:
        return nothing_yet(tidy(fig, "Finish rate"), "Too few readers to show yet")
    fig.add_scatter(
        x=days.local_day,
        y=daily,
        name="Each day",
        mode="markers",
        marker=dict(size=8, color=faded(colour, 0.3), line=dict(width=0)),
        customdata=days[["finished_reading", "opened_reading"]],
        hovertemplate=(
            "%{x|%a %-d %b}: %{y:.1%}<br>%{customdata[0]:,} of %{customdata[1]:,} readers"
            "<extra></extra>"
        ),
    )
    fig.add_scatter(
        x=days.local_day,
        y=weekly,
        name="Last 7 days",
        mode="lines",
        line=dict(width=3, color=colour),
        hovertemplate="Last 7 days: %{y:.1%}<extra></extra>",
    )
    # Show the whole story without squashing it: from just below the lowest day up to 100%
    lowest = float(np.nanmin(daily.to_numpy(dtype=float)))
    fig = tidy(
        fig,
        "Finish rate",
        "Readers who finished what they opened",
        legend=True,
    )
    fig.update_xaxes(tickformat=DAY_TICKS)
    fig.update_yaxes(tickformat=".0%", range=[min(0.5, lowest - 0.05), 1.02])
    return fig


def streak_survival(streaks: pd.DataFrame, persona: str) -> go.Figure:
    """How far streaks get (Kaplan-Meier), per persona for everyone, one curve otherwise."""
    fig = go.Figure()
    if streaks.empty:
        return nothing_yet(tidy(fig, "How far streaks get"))
    if len(streaks) < MIN_READERS:
        return nothing_yet(tidy(fig, "How far streaks get"), "Too few streaks to show yet")
    # A persona with only a few streaks would draw a confident line through noise
    shown = [p for p in data.PERSONAS if p != "all" and (streaks.persona == p).sum() >= MIN_READERS]
    for p in shown:
        curve = data.survival(streaks[streaks.persona == p])
        fig.add_scatter(
            x=curve.mornings,
            y=curve.reach,
            name=data.PERSONAS[p],
            mode="lines",
            line=dict(shape="hv", width=2.5, color=COLOURS[p]),
            hovertemplate=f"%{{x}} mornings · {data.PERSONAS[p]}: %{{y:.1%}}<extra></extra>",
        )
    week = data.survival(streaks).set_index("mornings").reach[7]
    fig.add_vline(x=7, line=dict(color=MUTED, width=1, dash="dot"))
    fig.add_annotation(
        x=7,
        y=0.97,
        xanchor="left",
        showarrow=False,
        font=dict(size=12, color=INK),
        text=f"  a week: <b>{week:.0%}</b> get here",
    )
    fig = tidy(
        fig,
        "How far streaks get",
        "Share lasting at least n mornings (Kaplan-Meier)",
        legend=True,
    )
    fig.update_layout(hovermode="x")
    fig.update_xaxes(range=[1, 30], dtick=7, tick0=0)
    fig.update_yaxes(tickformat=".0%", range=[0, 1.02])
    return fig


def who_comes_back(weeks: pd.DataFrame, persona: str) -> go.Figure:
    """Each signup week's share who read again on day 1, 7 and 30."""
    fig = go.Figure()
    if weeks.empty:
        return nothing_yet(tidy(fig, "Who comes back"))
    rates = pd.DataFrame(
        {
            f"day_{day}_rate": weeks[f"day_{day}_rate"]
            .astype(float)
            .where(weeks[f"day_{day}_eligible"] >= MIN_READERS)
            for day in (1, 7, 30)
        }
    )
    if rates.notna().sum().sum() == 0:
        return nothing_yet(tidy(fig, "Who comes back"), "Too few readers to show yet")
    fig.add_heatmap(
        z=rates.to_numpy(),
        x=["Day 1", "Day 7", "Day 30"],
        y=[f"Week of {d.day} {d:%b}" for d in weeks.cohort_week],
        colorscale=ramp(persona),
        zmin=0,
        zmax=float(np.nanmax(rates.to_numpy())),
        text=rates.map(lambda r: "" if pd.isna(r) else f"{r:.0%}").to_numpy(),
        texttemplate="%{text}",
        hoverongaps=False,
        xgap=3,
        ygap=3,
        customdata=weeks[["readers"]].to_numpy().repeat(3, axis=1),
        colorbar=dict(tickformat=".0%", thickness=8, outlinewidth=0, len=0.9),
        hovertemplate=(
            "%{y} (%{customdata:,} readers), %{x}: <b>%{z:.1%}</b> came back<extra></extra>"
        ),
    )
    fig = tidy(
        fig,
        "Who comes back",
        "Share of each signup week who read again",
    )
    fig.update_layout(margin_t=100)
    fig.update_xaxes(side="top", showgrid=False)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return fig


def sparkline(x, y, persona: str, from_zero: bool = True) -> go.Figure:
    """A tiny line for a tile: the shape of the last 90 days, no axes. y=None draws nothing."""
    colour = COLOURS[persona]
    if y is None:
        x, y = [], []
    fig = go.Figure(
        go.Scatter(
            x=x,
            y=y,
            mode="lines",
            line=dict(width=2, color=colour),
            hoverinfo="skip",
            fill="tozeroy" if from_zero else None,
            fillcolor=faded(colour, 0.12),
        )
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, rangemode="tozero" if from_zero else "normal")
    return fig
