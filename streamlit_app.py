# -*- coding: utf-8 -*-
"""Trainee performance dashboard built on top of Streamlit's stock peers demo."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Trainee performance dashboard",
    page_icon=":bar_chart:",
    layout="wide",
)

st.title(":material/query_stats: VR OPS Performance Dashboard")
st.write(
    "Monitor trainee accuracy trends with the neon styling you liked from the stock dashboard, and flip between mistakes and completion time views as needed."
)

st.markdown(
    """
    <style>
    div[data-testid="metric-container"] span[data-testid="stMetricValue"] {
        white-space: normal;
        word-break: break-word;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

DEFAULT_DATA_PATH = Path(__file__).parent / "trainee_performance_sample.xlsx"
STEP_NUMBERS = list(range(1, 9))
STEP_APPRAISAL_COLUMNS = [f"Step {step} Appraisal" for step in STEP_NUMBERS]
STEP_TIME_COLUMNS = [f"Step {step} Time" for step in STEP_NUMBERS]
REQUIRED_COLUMNS = [
    "Name",
    "Number of errors",
    "Completion Time (mins)",
    "Date",
    *STEP_APPRAISAL_COLUMNS,
    *STEP_TIME_COLUMNS,
]
HORIZON_OPTIONS = {
    "1 Day": timedelta(days=1),
    "1 Week": timedelta(weeks=1),
    "1 Month": timedelta(days=30),
    "3 Months": timedelta(days=90),
    "6 Months": timedelta(days=180),
    "1 Year": timedelta(days=365),
    "2 Years": timedelta(days=730),
    "3 Years": timedelta(days=1095),
}


def first_name(full_name: str) -> str:
    """Return the first token of a trainee name."""
    value = str(full_name).strip() if full_name else ""
    return value.split(" ", 1)[0] if value else ""


def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column types and keep only the fields the app needs."""
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}")

    cleaned = df.loc[:, REQUIRED_COLUMNS].copy()
    completion_dates = pd.to_datetime(cleaned["Date"], errors="coerce")
    errors = pd.to_numeric(cleaned["Number of errors"], errors="coerce")
    completion_minutes = pd.to_numeric(
        cleaned["Completion Time (mins)"], errors="coerce"
    )

    mask = completion_dates.notna() & completion_minutes.notna()
    cleaned = cleaned.loc[mask].copy()
    cleaned["Date"] = completion_dates.loc[mask]
    cleaned["Number of errors"] = (
        errors.loc[mask].fillna(0).round().astype(int)
    )
    cleaned["Completion Time (mins)"] = (
        completion_minutes.loc[mask].fillna(0).clip(lower=0)
    )
    cleaned["Name"] = cleaned["Name"].astype(str).str.strip()
    for step in STEP_NUMBERS:
        appraisal_col = f"Step {step} Appraisal"
        time_col = f"Step {step} Time"
        cleaned[appraisal_col] = (
            cleaned[appraisal_col].astype(str).str.strip().str.title()
        )
        cleaned.loc[~cleaned[appraisal_col].isin(["Right", "Wrong"]), appraisal_col] = pd.NA
        cleaned[time_col] = pd.to_numeric(cleaned[time_col], errors="coerce")

    cleaned = cleaned[cleaned["Name"] != ""]
    return cleaned.sort_values("Date").reset_index(drop=True)


@st.cache_data(ttl="1h", show_spinner=False)
def load_performance_data(path: Path | str) -> pd.DataFrame:
    """Load trainee data from disk and cache it for quick reloads."""
    return _prepare_dataframe(pd.read_excel(path))


def filter_by_horizon(df: pd.DataFrame, horizon_label: str) -> pd.DataFrame:
    """Subset the dataframe to only the rows that fall within the selected horizon."""
    if df.empty:
        return df

    latest_completion = df["Date"].max()
    time_window = latest_completion - HORIZON_OPTIONS[horizon_label]
    return df[df["Date"].between(time_window, latest_completion)]


def step_chart_records(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot step appraisal/time columns into long format with a Step 0 anchor."""
    records = []
    for step in STEP_NUMBERS:
        appraisal_col = f"Step {step} Appraisal"
        time_col = f"Step {step} Time"
        step_slice = df[["Name", "Session", "Date", appraisal_col, time_col]].rename(
            columns={
                appraisal_col: "Appraisal",
                time_col: "Step Time (mins)",
            }
        )
        step_slice["Step"] = step
        records.append(step_slice)

    combined = pd.concat(records, ignore_index=True)
    combined["Step Time (mins)"] = pd.to_numeric(combined["Step Time (mins)"], errors="coerce")
    combined = combined.dropna(subset=["Step Time (mins)"])
    combined.loc[~combined["Appraisal"].isin(["Right", "Wrong"]), "Appraisal"] = pd.NA

    anchors = df[["Name", "Session", "Date"]].drop_duplicates().copy()
    anchors["Appraisal"] = pd.NA
    anchors["Step Time (mins)"] = 0.0
    anchors["Step"] = 0

    combined = pd.concat([anchors, combined], ignore_index=True)
    return combined.sort_values(["Session", "Step"]).reset_index(drop=True)


def step_segment_records(step_points: pd.DataFrame) -> pd.DataFrame:
    """Build per-step area segments colored by the ending step's appraisal."""
    segments = []
    for session, session_rows in step_points.groupby("Session"):
        by_step = session_rows.sort_values("Step").set_index("Step")
        for step in STEP_NUMBERS:
            if step not in by_step.index or (step - 1) not in by_step.index:
                continue

            appraisal = by_step.loc[step, "Appraisal"]
            if pd.isna(appraisal) or appraisal not in {"Right", "Wrong"}:
                continue

            start_time = float(by_step.loc[step - 1, "Step Time (mins)"])
            end_time = float(by_step.loc[step, "Step Time (mins)"])
            session_date = by_step.loc[step, "Date"]
            segment_id = f"{session}|step-{step}"

            segments.append(
                {
                    "Session": session,
                    "Date": session_date,
                    "Segment": segment_id,
                    "Step": step - 1,
                    "Step Time (mins)": start_time,
                    "Appraisal": appraisal,
                }
            )
            segments.append(
                {
                    "Session": session,
                    "Date": session_date,
                    "Segment": segment_id,
                    "Step": step,
                    "Step Time (mins)": end_time,
                    "Appraisal": appraisal,
                }
            )

    if not segments:
        return pd.DataFrame()
    return pd.DataFrame(segments).sort_values(["Session", "Segment", "Step"])


cols = st.columns([1, 3])
top_left_cell = cols[0].container(
    border=True, height="stretch", vertical_alignment="center"
)
right_cell = cols[1].container(
    border=True, height="stretch", vertical_alignment="center"
)
bottom_left_cell = cols[0].container(
    border=True, height="stretch", vertical_alignment="center"
)

try:
    data = load_performance_data(DEFAULT_DATA_PATH)
    data_source_label = f"Sample data · {DEFAULT_DATA_PATH.name}"
except Exception as exc:  # noqa: BLE001 - surface friendly error to the UI
    top_left_cell.error(
        f"Unable to load the Excel file at {DEFAULT_DATA_PATH}: {exc}"
    )
    st.stop()

trainees = sorted(data["Name"].unique())
if not trainees:
    top_left_cell.warning("No trainee names were found in the dataset.")
    st.stop()

with top_left_cell:
    st.caption(f"Data source: {data_source_label}")
    selected_trainees = st.multiselect(
        "Trainees",
        options=trainees,
        default=trainees,
        placeholder="Choose trainees to compare. Example: Emily Chen",
    )
    horizon = st.pills(
        "Time horizon",
        options=list(HORIZON_OPTIONS.keys()),
        default="3 Months",
    )

if not selected_trainees:
    top_left_cell.info("Pick at least one trainee to populate the dashboard.")
    st.stop()

main_filtered = data[data["Name"].isin(selected_trainees)].copy()
filtered = filter_by_horizon(main_filtered, horizon)

if filtered.empty:
    top_left_cell.warning(
        "No records match that trainee list and time horizon. "
        "Try widening the range."
    )
else:
    error_totals = filtered.groupby("Name")["Number of errors"].sum()
    best_name = error_totals.idxmin()
    worst_name = error_totals.idxmax()

    with bottom_left_cell:
        metric_cols = st.columns(2)
        metric_cols[0].metric(
            "Best employee",
            first_name(best_name),
            delta=f"{error_totals[best_name]} errors",
            delta_color="normal",
            width="content",
        )
        metric_cols[1].metric(
            "Needs attention",
            first_name(worst_name),
            delta=f"{error_totals[worst_name]} errors",
            delta_color="inverse",
            width="content",
        )

    chart_data = filtered.sort_values("Date")

    with right_cell:
        show_completion = st.toggle(
            "Trainee Error and Completion Trends",
            value=False,
            help="Switch the main chart between mistakes and completion time.",
        )
        y_field = "Completion Time (mins)" if show_completion else "Number of errors"
        y_title = "Completion time (mins)" if show_completion else "Number of mistakes"

        st.altair_chart(
            alt.Chart(chart_data)
            .mark_line(point=True)
            .encode(
                alt.X("Date:T", title="Date"),
                alt.Y(f"{y_field}:Q", title=y_title, scale=alt.Scale(zero=False)),
                alt.Color("Name:N", title="Trainee"),
                tooltip=[
                    "Name",
                    "Date",
                    "Number of errors",
                    "Completion Time (mins)",
                ],
            )
            .properties(height=420),
            use_container_width=True,
        )

step_cols = st.columns([1, 3])
step_filter_cell = step_cols[0].container(
    border=True, height="stretch", vertical_alignment="top"
)
step_chart_cell = step_cols[1].container(
    border=True, height="stretch", vertical_alignment="center"
)

step_source = main_filtered.sort_values("Date")
step_trainees = sorted(step_source["Name"].unique())

with step_filter_cell:
    st.subheader("Step chart filters")
    selected_step_trainee = st.selectbox(
        "Trainee",
        options=step_trainees,
    )

selected_step_rows = (
    step_source[step_source["Name"] == selected_step_trainee]
    .sort_values("Date")
    .reset_index(drop=True)
)
selected_step_rows["Session"] = (
    "Session "
    + (selected_step_rows.index + 1).astype(str)
    + " | "
    + selected_step_rows["Date"].dt.strftime("%Y-%m-%d %H:%M")
)
date_min = selected_step_rows["Date"].min().date()
date_max = selected_step_rows["Date"].max().date()

with step_filter_cell:
    selected_date_range = st.date_input(
        "Date range",
        value=(date_min, date_max),
        min_value=date_min,
        max_value=date_max,
    )
    last_session_only = st.button(
        "Last Session",
        use_container_width=True,
        help="Show only the most recent session for the selected trainee.",
    )

single_date_selected = False
if isinstance(selected_date_range, (tuple, list)):
    if len(selected_date_range) == 2:
        step_start_date, step_end_date = selected_date_range
    elif len(selected_date_range) == 1:
        single_date_selected = True
    else:
        single_date_selected = True
else:
    single_date_selected = True

if last_session_only:
    step_filtered = selected_step_rows.tail(1)
    step_records = step_chart_records(step_filtered)
    step_segments = step_segment_records(step_records)

    if step_records.empty or step_segments.empty:
        step_chart_cell.info("No step records found for the last session.")
    else:
        fill_palette = ["#86efac", "#fca5a5"]
        session_count = step_records["Session"].nunique()

        with step_chart_cell:
            st.subheader("Individual Perfromance Review")
            x_axis = alt.X(
                "Step:Q",
                title="Step",
                scale=alt.Scale(domain=[0, 8], nice=False),
                axis=alt.Axis(values=list(range(0, 9))),
            )
            y_axis = alt.Y(
                "Step Time (mins):Q",
                title="Time (mins)",
                scale=alt.Scale(domainMin=0),
                stack=None,
            )

            fill_chart = alt.Chart(step_segments).mark_area(
                opacity=0.24,
                interpolate="linear",
            ).encode(
                x_axis,
                y_axis,
                detail="Segment:N",
                color=alt.Color(
                    "Appraisal:N",
                    scale=alt.Scale(
                        domain=["Right", "Wrong"],
                        range=fill_palette,
                    ),
                    legend=alt.Legend(title="Segment fill"),
                ),
                tooltip=[
                    alt.Tooltip("Session:N", title="Session"),
                    alt.Tooltip("Date:T", title="Date"),
                    alt.Tooltip("Step:Q", title="Step"),
                    alt.Tooltip("Appraisal:N", title="Appraisal"),
                    alt.Tooltip("Step Time (mins):Q", title="Step time (mins)", format=".2f"),
                ],
            )

            line_chart = alt.Chart(step_records).mark_line(
                color="#cbd5e1", strokeWidth=2.1, interpolate="linear"
            ).encode(
                x_axis,
                y_axis,
                detail="Session:N",
                strokeDash=alt.StrokeDash(
                    "Session:N",
                    legend=alt.Legend(title="Session", orient="bottom"),
                ),
                tooltip=[
                    alt.Tooltip("Session:N", title="Session"),
                    alt.Tooltip("Date:T", title="Date"),
                    alt.Tooltip("Step:Q", title="Step"),
                    alt.Tooltip("Appraisal:N", title="Appraisal"),
                    alt.Tooltip("Step Time (mins):Q", title="Step time (mins)", format=".2f"),
                ],
            )

            if session_count == 1:
                line_chart = alt.Chart(step_records).mark_line(
                    color="#cbd5e1", strokeWidth=2.1, interpolate="linear"
                ).encode(
                    x_axis,
                    y_axis,
                    detail="Session:N",
                    tooltip=[
                        alt.Tooltip("Session:N", title="Session"),
                        alt.Tooltip("Date:T", title="Date"),
                        alt.Tooltip("Step:Q", title="Step"),
                        alt.Tooltip("Appraisal:N", title="Appraisal"),
                        alt.Tooltip(
                            "Step Time (mins):Q",
                            title="Step time (mins)",
                            format=".2f",
                        ),
                    ],
                )

            st.altair_chart(
                (fill_chart + line_chart).properties(height=350),
                use_container_width=True,
            )
elif single_date_selected:
    step_chart_cell.caption(
        "Please select both a start date and an end date to define the date range."
    )
else:
    step_filtered = selected_step_rows[
        selected_step_rows["Date"].between(
            pd.Timestamp(step_start_date),
            pd.Timestamp(step_end_date)
            + pd.Timedelta(days=1)
            - pd.Timedelta(seconds=1),
        )
    ]

    step_records = step_chart_records(step_filtered)
    step_segments = step_segment_records(step_records)

    if step_records.empty or step_segments.empty:
        step_chart_cell.info("No step records match the selected trainee and date range.")
    else:
        fill_palette = ["#86efac", "#fca5a5"]
        session_count = step_records["Session"].nunique()

        with step_chart_cell:
            st.subheader("Individual Perfromance Review")
            x_axis = alt.X(
                "Step:Q",
                title="Step",
                scale=alt.Scale(domain=[0, 8], nice=False),
                axis=alt.Axis(values=list(range(0, 9))),
            )
            y_axis = alt.Y(
                "Step Time (mins):Q",
                title="Time (mins)",
                scale=alt.Scale(domainMin=0),
                stack=None,
            )

            fill_chart = alt.Chart(step_segments).mark_area(
                opacity=0.24,
                interpolate="linear",
            ).encode(
                x_axis,
                y_axis,
                detail="Segment:N",
                color=alt.Color(
                    "Appraisal:N",
                    scale=alt.Scale(
                        domain=["Right", "Wrong"],
                        range=fill_palette,
                    ),
                    legend=alt.Legend(title="Segment fill"),
                ),
                tooltip=[
                    alt.Tooltip("Session:N", title="Session"),
                    alt.Tooltip("Date:T", title="Date"),
                    alt.Tooltip("Step:Q", title="Step"),
                    alt.Tooltip("Appraisal:N", title="Appraisal"),
                    alt.Tooltip("Step Time (mins):Q", title="Step time (mins)", format=".2f"),
                ],
            )

            line_chart = alt.Chart(step_records).mark_line(
                color="#cbd5e1", strokeWidth=2.1, interpolate="linear"
            ).encode(
                x_axis,
                y_axis,
                detail="Session:N",
                strokeDash=alt.StrokeDash(
                    "Session:N",
                    legend=alt.Legend(title="Session", orient="bottom"),
                ),
                tooltip=[
                    alt.Tooltip("Session:N", title="Session"),
                    alt.Tooltip("Date:T", title="Date"),
                    alt.Tooltip("Step:Q", title="Step"),
                    alt.Tooltip("Appraisal:N", title="Appraisal"),
                    alt.Tooltip("Step Time (mins):Q", title="Step time (mins)", format=".2f"),
                ],
            )

            if session_count == 1:
                line_chart = alt.Chart(step_records).mark_line(
                    color="#cbd5e1", strokeWidth=2.1, interpolate="linear"
                ).encode(
                    x_axis,
                    y_axis,
                    detail="Session:N",
                    tooltip=[
                        alt.Tooltip("Session:N", title="Session"),
                        alt.Tooltip("Date:T", title="Date"),
                        alt.Tooltip("Step:Q", title="Step"),
                        alt.Tooltip("Appraisal:N", title="Appraisal"),
                        alt.Tooltip(
                            "Step Time (mins):Q",
                            title="Step time (mins)",
                            format=".2f",
                        ),
                    ],
                )

            st.altair_chart(
                (fill_chart + line_chart).properties(height=350),
                use_container_width=True,
            )
