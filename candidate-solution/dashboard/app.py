# ruff: noqa: E501  # Embedded CSS and HTML are clearer as complete lines.
import os
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://agent_user:agent_password@postgres:5432/gen_ai_agent_db",
)

st.set_page_config(
    page_title="PIA GeoVision Analytics",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def database_engine():
    return create_engine(DATABASE_URL, pool_pre_ping=True)


@st.cache_data(ttl=10)
def load_metrics() -> pd.DataFrame:
    with database_engine().connect() as connection:
        return pd.read_sql(
            text("SELECT * FROM analytics_metrics ORDER BY metric_date, city"), connection
        )


def format_number(value: float | int) -> str:
    """Format large dashboard numbers without hiding their scale."""
    absolute = abs(value)
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.1f} M"
    if absolute >= 1_000:
        return f"{value / 1_000:.1f} K"
    return f"{value:,.0f}"


def weighted_average(frame: pd.DataFrame, value_column: str) -> float:
    weights = frame["total_transactions"].fillna(0)
    values = frame[value_column].fillna(0)
    return float((values * weights).sum() / max(weights.sum(), 1))


def percentage_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return (current - previous) / previous * 100


def change_label(value: float | None, suffix: str = "vs. período anterior") -> str:
    if value is None:
        return "Sin período comparable"
    return f"{value:+.1f}% {suffix}"


def reset_filters() -> None:
    for key in ("country_filter", "city_filter", "date_filter"):
        st.session_state.pop(key, None)


def chart_layout(height: int = 330, show_legend: bool = False) -> dict:
    return {
        "height": height,
        "margin": {"l": 16, "r": 16, "t": 48, "b": 16},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": "Inter, sans-serif", "color": "#475569", "size": 12},
        "title_font": {"color": "#0f172a", "size": 16},
        "title_x": 0.01,
        "title_xanchor": "left",
        "showlegend": show_legend,
        "hoverlabel": {
            "bgcolor": "#0f172a",
            "font_color": "white",
            "bordercolor": "#0f172a",
        },
    }


st.markdown(
    """
    <style>
    :root { --ink:#0f172a; --muted:#64748b; --line:#e2e8f0; --brand:#2563eb; }
    html, body, [class*="css"] { font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif; }
    .stApp { background:#f7f9fc; color:var(--ink); }
    [data-testid="stHeader"] { background:transparent; }
    [data-testid="stToolbar"] { right:1rem; }
    .block-container { max-width:1500px; padding:1.6rem 2.2rem 3rem; }
    [data-testid="stSidebar"] { background:#0b1220; border-right:0; }
    [data-testid="stSidebar"] * { color:#e2e8f0; }
    [data-testid="stSidebar"] .stMultiSelect label,
    [data-testid="stSidebar"] .stDateInput label { color:#94a3b8; font-size:.78rem; font-weight:600; }
    [data-testid="stSidebar"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] [data-baseweb="input"] > div { background:#131e30; border-color:#26354b; }
    [data-testid="stSidebar"] hr { border-color:#233047; }
    .brand { display:flex; align-items:center; gap:.75rem; margin:.25rem 0 1.6rem; }
    .brand-mark { width:36px; height:36px; border-radius:10px; background:linear-gradient(135deg,#3b82f6,#22d3ee); display:grid; place-items:center; color:white; font-weight:700; box-shadow:0 8px 24px #2563eb44; }
    .brand-name { color:white; font-weight:700; font-size:1rem; line-height:1.1; }
    .brand-sub { color:#64748b; font-size:.7rem; margin-top:.2rem; letter-spacing:.08em; }
    .topbar { display:flex; justify-content:space-between; align-items:flex-start; gap:2rem; margin-bottom:1.35rem; }
    .eyebrow { color:#2563eb; font-size:.72rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase; margin-bottom:.35rem; }
    .page-title { color:#0f172a; font-size:1.8rem; font-weight:700; letter-spacing:-.035em; line-height:1.2; }
    .page-subtitle { color:#64748b; font-size:.86rem; margin-top:.35rem; }
    .live-pill { display:inline-flex; align-items:center; gap:.45rem; white-space:nowrap; color:#166534; background:#ecfdf3; border:1px solid #bbf7d0; border-radius:999px; padding:.45rem .75rem; font-size:.72rem; font-weight:600; }
    .live-dot { width:7px; height:7px; background:#22c55e; border-radius:50%; box-shadow:0 0 0 4px #22c55e20; }
    [data-testid="stMetric"] { background:white; border:1px solid var(--line); border-radius:14px; padding:1rem 1.1rem; box-shadow:0 2px 10px #0f172a08; min-height:126px; }
    [data-testid="stMetricLabel"] { color:#64748b; font-size:.76rem; font-weight:600; }
    [data-testid="stMetricValue"] { color:#0f172a; font-size:1.65rem; font-weight:700; letter-spacing:-.035em; }
    [data-testid="stMetricDelta"] { font-size:.7rem; }
    [data-testid="stPlotlyChart"] { background:white; border:1px solid var(--line); border-radius:14px; box-shadow:0 2px 10px #0f172a08; overflow:hidden; }
    .section-head { margin:1.65rem 0 .75rem; }
    .section-title { color:#0f172a; font-size:1rem; font-weight:700; }
    .section-copy { color:#94a3b8; font-size:.75rem; margin-top:.15rem; }
    .insight-card { height:100%; min-height:330px; box-sizing:border-box; background:linear-gradient(145deg,#0f172a,#172554); color:white; border-radius:14px; padding:1.4rem; box-shadow:0 8px 26px #0f172a18; }
    .insight-kicker { color:#7dd3fc; font-size:.68rem; font-weight:700; letter-spacing:.12em; }
    .insight-title { font-size:1.15rem; font-weight:650; line-height:1.35; margin:.75rem 0 1.25rem; }
    .insight-row { display:flex; justify-content:space-between; gap:1rem; border-top:1px solid #ffffff18; padding:.78rem 0; }
    .insight-label { color:#94a3b8; font-size:.72rem; }
    .insight-value { color:#f8fafc; font-size:.76rem; font-weight:600; text-align:right; }
    .footnote { color:#94a3b8; font-size:.68rem; margin:.55rem 0 0; }
    [data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:12px; overflow:hidden; }
    .stAlert { border-radius:12px; }
    @media (max-width:900px) { .block-container { padding:1rem; } .topbar { flex-direction:column; gap:.75rem; } }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown(
        """
        <div class="brand">
          <div class="brand-mark">P</div>
          <div><div class="brand-name">PIA GeoVision Analytics</div><div class="brand-sub">OPERATIONS INTELLIGENCE</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

try:
    data = load_metrics()
except Exception as exc:
    st.error("No fue posible consultar PostgreSQL. Verifica que el servicio esté disponible.")
    with st.expander("Ver detalle técnico"):
        st.exception(exc)
    st.stop()

if data.empty:
    st.info("Aún no hay métricas. Envía transacciones desde el servicio del puerto 8002.")
    st.stop()

data["metric_date"] = pd.to_datetime(data["metric_date"])
data["city"] = data["city"].fillna("Sin ciudad")
data["country"] = data["country"].fillna("Sin país")

with st.sidebar:
    countries = sorted(data["country"].unique())
    date_min = data["metric_date"].min().date()
    date_max = data["metric_date"].max().date()
    with st.expander("Filtros", expanded=False):
        selected_dates = st.date_input(
            "Período",
            value=(date_min, date_max),
            min_value=date_min,
            max_value=date_max,
            format="DD/MM/YYYY",
            key="date_filter",
        )
        selected_countries = st.multiselect(
            "País", countries, default=countries, key="country_filter"
        )
        available_cities = sorted(
            data.loc[data["country"].isin(selected_countries), "city"].unique()
        )
        selected_cities = st.multiselect(
            "Ciudad", available_cities, default=available_cities, key="city_filter"
        )
        st.divider()
        st.button(
            "Restablecer filtros",
            width="stretch",
            on_click=reset_filters,
        )

filtered = data[data["country"].isin(selected_countries) & data["city"].isin(selected_cities)]
if isinstance(selected_dates, tuple | list) and len(selected_dates) == 2:
    start, end = pd.Timestamp(selected_dates[0]), pd.Timestamp(selected_dates[1])
    filtered = filtered[filtered["metric_date"].between(start, end)]
else:
    start = end = pd.Timestamp(selected_dates)
    filtered = filtered[filtered["metric_date"].eq(start)]

if filtered.empty:
    st.warning("No hay datos para la combinación de filtros seleccionada.")
    st.stop()

last_refresh = datetime.now().strftime("%H:%M")
period_label = (
    f"{filtered['metric_date'].min():%d %b %Y} — {filtered['metric_date'].max():%d %b %Y}"
)
st.markdown(
    f"""
    <div class="topbar"><div>
    <div class="page-title">Métricas globales</div>
    <div class="page-subtitle">{period_label} · {filtered["city"].nunique()} ciudades · {filtered["country"].nunique()} países</div>
    </div><div class="live-pill"><span class="live-dot"></span> Datos actualizados · {last_refresh}</div></div>
    """,
    unsafe_allow_html=True,
)

total_transactions = int(filtered["total_transactions"].sum())
total_users = int(filtered["unique_users"].sum())
total_tokens = int(filtered["total_tokens_used"].sum())
avg_response = weighted_average(filtered, "avg_response_time_ms")
tokens_per_transaction = total_tokens / max(total_transactions, 1)

period_days = max((end - start).days + 1, 1)
previous_end = start - pd.Timedelta(days=1)
previous_start = previous_end - pd.Timedelta(days=period_days - 1)
previous = data[
    data["country"].isin(selected_countries)
    & data["city"].isin(selected_cities)
    & data["metric_date"].between(previous_start, previous_end)
]
previous_transactions = int(previous["total_transactions"].sum())
previous_users = int(previous["unique_users"].sum())
previous_tokens = int(previous["total_tokens_used"].sum())
previous_response = weighted_average(previous, "avg_response_time_ms") if not previous.empty else 0

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
kpi1.metric(
    "Transacciones",
    format_number(total_transactions),
    change_label(percentage_change(total_transactions, previous_transactions)),
)
kpi2.metric(
    "Usuarios activos*",
    format_number(total_users),
    change_label(percentage_change(total_users, previous_users)),
)
kpi3.metric(
    "Tokens consumidos",
    format_number(total_tokens),
    change_label(percentage_change(total_tokens, previous_tokens)),
)
kpi4.metric(
    "Tiempo de respuesta",
    f"{avg_response:,.0f} ms",
    change_label(percentage_change(avg_response, previous_response)),
    delta_color="inverse",
)
kpi5.metric("Tokens / transacción", f"{tokens_per_transaction:,.0f}", "Eficiencia de consumo")
st.markdown(
    '<div class="footnote">* Suma de usuarios únicos por ciudad y día; una persona puede aparecer en más de un grupo.</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="section-head"><div class="section-title">Insights del negocio</div><div class="section-copy">Volumen, distribución geográfica y señales operativas del período</div></div>',
    unsafe_allow_html=True,
)

timeline = filtered.groupby("metric_date", as_index=False).agg(
    total_transactions=("total_transactions", "sum")
)
fig_timeline = go.Figure()
fig_timeline.add_trace(
    go.Scatter(
        x=timeline["metric_date"],
        y=timeline["total_transactions"],
        mode="lines+markers",
        line={"color": "#2563eb", "width": 3, "shape": "spline"},
        marker={"size": 7, "color": "white", "line": {"color": "#2563eb", "width": 2}},
        fill="tozeroy",
        fillcolor="rgba(37,99,235,.08)",
        hovertemplate="%{x|%d %b}<br><b>%{y:,.0f}</b> transacciones<extra></extra>",
    )
)
fig_timeline.update_layout(title="Evolución de transacciones", **chart_layout(height=350))
fig_timeline.update_xaxes(showgrid=False, title=None, tickformat="%d %b", color="#94a3b8")
fig_timeline.update_yaxes(gridcolor="#edf2f7", title=None, rangemode="tozero", color="#94a3b8")

by_city = (
    filtered.groupby(["city", "country"], as_index=False)["total_transactions"]
    .sum()
    .sort_values("total_transactions", ascending=True)
    .tail(8)
)
fig_city = px.bar(
    by_city,
    x="total_transactions",
    y="city",
    orientation="h",
    color="total_transactions",
    color_continuous_scale=[[0, "#bfdbfe"], [1, "#2563eb"]],
    custom_data=["country"],
)
fig_city.update_traces(
    hovertemplate="%{y}, %{customdata[0]}<br><b>%{x:,.0f}</b> transacciones<extra></extra>",
    marker_line_width=0,
)
fig_city.update_layout(
    title="Ciudades con mayor actividad", coloraxis_showscale=False, **chart_layout(height=350)
)
fig_city.update_xaxes(gridcolor="#edf2f7", title=None, color="#94a3b8")
fig_city.update_yaxes(showgrid=False, title=None, color="#475569")

left, right = st.columns([1.55, 1])
left.plotly_chart(fig_timeline, width="stretch", config={"displayModeBar": False})
right.plotly_chart(fig_city, width="stretch", config={"displayModeBar": False})

sentiment_values = {
    "Positivo": int(filtered["positive_sentiment_count"].sum()),
    "Neutral": int(filtered["neutral_sentiment_count"].sum()),
    "Negativo": int(filtered["negative_sentiment_count"].sum()),
}
urgency_values = {
    "Alta": int(filtered["high_urgency_count"].sum()),
    "Media": int(filtered["medium_urgency_count"].sum()),
    "Baja": int(filtered["low_urgency_count"].sum()),
}

sentiment = pd.DataFrame(
    {"Sentimiento": sentiment_values.keys(), "Transacciones": sentiment_values.values()}
)
fig_sentiment = px.pie(
    sentiment,
    names="Sentimiento",
    values="Transacciones",
    hole=0.67,
    color="Sentimiento",
    color_discrete_map={"Positivo": "#10b981", "Neutral": "#cbd5e1", "Negativo": "#f97316"},
)
fig_sentiment.update_traces(
    textinfo="percent",
    textfont_size=11,
    marker={"line": {"color": "white", "width": 3}},
    hovertemplate="%{label}<br><b>%{value:,.0f}</b> · %{percent}<extra></extra>",
)
fig_sentiment.update_layout(
    title="Sentimiento de interacciones", **chart_layout(height=330, show_legend=True)
)
fig_sentiment.update_layout(legend={"orientation": "h", "y": -0.05, "x": 0.5, "xanchor": "center"})
fig_sentiment.add_annotation(
    text=f"<b>{format_number(sum(sentiment_values.values()))}</b><br><span style='font-size:10px;color:#94a3b8'>analizadas</span>",
    x=0.5,
    y=0.5,
    showarrow=False,
    font={"size": 18, "color": "#0f172a"},
)

urgency = pd.DataFrame(
    {"Urgencia": urgency_values.keys(), "Transacciones": urgency_values.values()}
)
fig_urgency = px.bar(
    urgency,
    x="Urgencia",
    y="Transacciones",
    color="Urgencia",
    color_discrete_map={"Alta": "#ef4444", "Media": "#f59e0b", "Baja": "#38bdf8"},
    text_auto=",.0f",
)
fig_urgency.update_traces(
    marker_line_width=0,
    textposition="outside",
    hovertemplate="%{x}<br><b>%{y:,.0f}</b> transacciones<extra></extra>",
)
fig_urgency.update_layout(title="Nivel de urgencia", **chart_layout(height=330))
fig_urgency.update_xaxes(showgrid=False, title=None, color="#64748b")
fig_urgency.update_yaxes(gridcolor="#edf2f7", title=None, rangemode="tozero", color="#94a3b8")

top_city_row = by_city.iloc[-1]
positive_share = sentiment_values["Positivo"] / max(sum(sentiment_values.values()), 1) * 100
high_urgency_share = urgency_values["Alta"] / max(sum(urgency_values.values()), 1) * 100
query_modes = filtered["most_common_query_type"].dropna().mode()
top_query = query_modes.iloc[0].replace("_", " ").title() if not query_modes.empty else "Sin datos"
peak_hours = filtered["peak_hour"].dropna().mode()
peak_hour = f"{int(peak_hours.iloc[0]):02d}:00" if not peak_hours.empty else "—"

chart_col1, chart_col2, insight_col = st.columns([1, 1, 0.9])
chart_col1.plotly_chart(fig_sentiment, width="stretch", config={"displayModeBar": False})
chart_col2.plotly_chart(fig_urgency, width="stretch", config={"displayModeBar": False})
with insight_col:
    st.markdown(
        f"""
    <div class="insight-card"><div class="insight-kicker">LECTURA EJECUTIVA</div>
    <div class="insight-title">La operación concentra su mayor volumen en {top_city_row["city"]}.</div>
    <div class="insight-row"><span class="insight-label">Ciudad líder</span><span class="insight-value">{top_city_row["city"]} · {int(top_city_row["total_transactions"]):,}</span></div>
    <div class="insight-row"><span class="insight-label">Sentimiento positivo</span><span class="insight-value">{positive_share:.1f}%</span></div>
    <div class="insight-row"><span class="insight-label">Casos de alta urgencia</span><span class="insight-value">{high_urgency_share:.1f}%</span></div>
    <div class="insight-row"><span class="insight-label">Consulta dominante</span><span class="insight-value">{top_query}</span></div>
    <div class="insight-row"><span class="insight-label">Hora pico</span><span class="insight-value">{peak_hour}</span></div></div>
    """,
        unsafe_allow_html=True,
    )

st.markdown(
    '<div class="section-head"><div class="section-title">Detalle de desempeño</div><div class="section-copy">Desglose diario por ubicación para análisis y seguimiento</div></div>',
    unsafe_allow_html=True,
)

display_columns = [
    "metric_date",
    "country",
    "city",
    "total_transactions",
    "unique_users",
    "avg_response_time_ms",
    "total_tokens_used",
    "most_common_query_type",
    "peak_hour",
]
detail = filtered[display_columns].sort_values(
    ["metric_date", "total_transactions"], ascending=[False, False]
)
st.dataframe(
    detail,
    width="stretch",
    hide_index=True,
    height=390,
    column_config={
        "metric_date": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
        "country": st.column_config.TextColumn("País"),
        "city": st.column_config.TextColumn("Ciudad"),
        "total_transactions": st.column_config.NumberColumn("Transacciones", format="%d"),
        "unique_users": st.column_config.NumberColumn("Usuarios*", format="%d"),
        "avg_response_time_ms": st.column_config.NumberColumn("Respuesta", format="%.0f ms"),
        "total_tokens_used": st.column_config.NumberColumn("Tokens", format="%d"),
        "most_common_query_type": st.column_config.TextColumn("Consulta principal"),
        "peak_hour": st.column_config.NumberColumn("Hora pico", format="%02d h"),
    },
)
