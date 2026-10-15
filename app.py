import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import plotly.express as px
from datetime import datetime, timezone, date, time as dt_time

# ----------------- Seiten-Konfiguration -----------------
st.set_page_config(page_title="Cycle Trendwechsel Profiler", page_icon="🔄", layout="wide")

st.title("🔄 Zyklus-Trendwende Profiler (PZP)")
st.caption("Analysiert, an welchen Positionen innerhalb eines Zyklus sich historische Trendwechsel wiederholen (inkl. minutengenauer Startzeit).")

# US-kompatible Datenquelle (Kraken)
@st.cache_resource
def get_exchange():
    return ccxt.kraken({
        'enableRateLimit': True,
    })

exchange = get_exchange()

# Timeframe Konfigurationen
TF_CONFIG = {
    "15m": {"fetch_tf": "15m", "resample": None,  "limit": 720},
    "30m": {"fetch_tf": "30m", "resample": None,  "limit": 720},
    "1h":  {"fetch_tf": "1h",  "resample": None,  "limit": 720},
    "2h":  {"fetch_tf": "1h",  "resample": "2h",  "limit": 720},
    "4h":  {"fetch_tf": "4h",  "resample": None,  "limit": 720},
    "1d":  {"fetch_tf": "1d",  "resample": None,  "limit": 720},
    "2d":  {"fetch_tf": "1d",  "resample": "2D",  "limit": 720},
    "3d":  {"fetch_tf": "1d",  "resample": "3D",  "limit": 720},
    "4d":  {"fetch_tf": "1d",  "resample": "4D",  "limit": 720},
    "1w":  {"fetch_tf": "1w",  "resample": None,  "limit": 500}
}

# ----------------- Sidebar / Parameter -----------------
with st.sidebar:
    st.header("⚙️ Markt & Zyklus")
    
    # Asset-Auswahl
    market_list = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK", "NEAR"]
    selected_coin = st.selectbox("Markt / Asset", options=market_list, index=0)
    
    tf_options = list(TF_CONFIG.keys())
    tf_choice = st.selectbox("Timeframe", options=tf_options, index=tf_options.index("1h"))
    
    st.markdown("---")
    st.subheader("🔁 Zyklus-Einstellungen")
    cycle_length = st.number_input("Zykluslänge (in Kerzen/Bars)", min_value=3, max_value=150, value=24, step=1)
    cycle_count = st.number_input("Anzahl zu vergleichender Zyklen", min_value=2, max_value=40, value=10, step=1)
    
    st.markdown("##### Startzeitpunkt des 1. Zyklus")
    col_d, col_t = st.columns([1, 1])
    with col_d:
        start_date_input = st.date_input("Startdatum", value=date(2024, 1, 1))
    with col_t:
        start_time_input = st.time_input("Startuhrzeit (UTC)", value=dt_time(0, 0), step=300)
    
    st.caption("ℹ️ Die Uhrzeit wird standardmäßig in **UTC** interpretiert (Börsen-Standard).")
    
    st.markdown("---")
    st.subheader("📐 PZP-Algorithmus Parameter")
    pL = st.number_input("Pivot Links (L)", min_value=1, value=2)
    pR = st.number_input("Pivot Rechts (R)", min_value=1, value=2)
    factor = st.number_input("Projektionsfaktor", min_value=0.05, value=0.5, step=0.05)
    
    btn_run = st.button("🚀 Analyse starten", use_container_width=True)

# ----------------- Daten abrufen -----------------
def fetch_candles(coin, tf_choice):
    cfg = TF_CONFIG[tf_choice]
    symbol = f"{coin}/USD"
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=cfg["fetch_tf"], limit=cfg["limit"])
    if not ohlcv or len(ohlcv) < 30:
        return None
    
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df.set_index('timestamp', inplace=True)
    
    if cfg["resample"]:
        df = df.resample(cfg["resample"]).agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()
        
    return df

# ----------------- PZP Trendwechsel-Erkennung -----------------
def identify_trend_changes(df, L, R, f):
    highs = df['High'].values
    lows = df['Low'].values
    n = len(df)
    
    has_turn = np.zeros(n, dtype=bool)
    
    ph_indices = []
    pl_indices = []
    
    for i in range(L, n - R):
        if all(highs[i] > highs[i - k] for k in range(1, L + 1)) and all(highs[i] > highs[i + k] for k in range(1, R + 1)):
            ph_indices.append(i)
            if len(ph_indices) >= 2:
                dist = np.ceil(f * (ph_indices[-1] - ph_indices[-2]))
                target_bar = int(ph_indices[-1] + dist + R)
                if target_bar < n:
                    has_turn[target_bar] = True
                    
        if all(lows[i] < lows[i - k] for k in range(1, L + 1)) and all(lows[i] < lows[i + k] for k in range(1, R + 1)):
            pl_indices.append(i)
            if len(pl_indices) >= 2:
                dist = np.ceil(f * (pl_indices[-1] - pl_indices[-2]))
                target_bar = int(pl_indices[-1] + dist + R)
                if target_bar < n:
                    has_turn[target_bar] = True

    df['has_turn'] = has_turn
    return df

# ----------------- Hauptausführung -----------------
with st.spinner(f"Lade historische Kursdaten für {selected_coin}..."):
    df_raw = fetch_candles(selected_coin, tf_choice)

if df_raw is None or len(df_raw) < 50:
    st.error("Fehler beim Laden der Kursdaten oder zu wenige Daten verfügbar.")
    st.stop()

# Trendwenden berechnen
df = identify_trend_changes(df_raw, pL, pR, factor)

# Exakten Startzeitpunkt aus Datum + Uhrzeit kombinieren (UTC)
start_dt = pd.to_datetime(datetime.combine(start_date_input, start_time_input)).tz_localize('UTC')
df_sub = df[df.index >= start_dt].copy()

total_needed_bars = cycle_count * cycle_length

if len(df_sub) < total_needed_bars:
    available_cycles = len(df_sub) // cycle_length
    st.warning(f"Ab dem gewählten Startzeitpunkt ({start_dt.strftime('%d.%m.%Y %H:%M UTC')}) stehen {len(df_sub)} Kerzen zur Verfügung. Für {cycle_count} Zyklen werden {total_needed_bars} Kerzen benötigt.")
    if available_cycles < 2:
        st.error(f"Bitte wähle einen früheren Startzeitpunkt oder eine kleinere Zykluslänge (aktuell möglich: {available_cycles} Zyklen).")
        st.stop()
    else:
        st.info(f"Analyse wird automatisch auf die maximal verfügbaren {available_cycles} Zyklen angepasst.")
        cycle_count = available_cycles

# Zyklen und Bar-Positionen exakt ab der ersten Kerze zuweisen
df_cycles = df_sub.iloc[:cycle_count * cycle_length].copy()
cycle_ids = []
positions_in_cycle = []

for idx in range(len(df_cycles)):
    cycle_ids.append(idx // cycle_length + 1)
    positions_in_cycle.append(idx % cycle_length)

df_cycles['Cycle_ID'] = cycle_ids
df_cycles['Position'] = positions_in_cycle

# ----------------- Statistik berechnen -----------------
position_stats = []

for pos in range(cycle_length):
    turns_at_pos = df_cycles[(df_cycles['Position'] == pos) & (df_cycles['has_turn'] == True)]
    unique_cycles_with_turn = turns_at_pos['Cycle_ID'].nunique()
    pct = round((unique_cycles_with_turn / cycle_count) * 100, 1)
    
    position_stats.append({
        "Position": pos,
        "Trendwechsel (Anzahl Zyklen)": f"{unique_cycles_with_turn} / {cycle_count}",
        "Trefferquote (%)": pct
    })

stats_df = pd.DataFrame(position_stats)

# ----------------- UI / Darstellung -----------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Untersuchte Zyklen", f"{cycle_count}")
col2.metric("Zykluslänge", f"{cycle_length} Kerzen ({tf_choice})")
col3.metric("Zyklus 1 Start", f"{df_cycles.index[0].strftime('%d.%m. %H:%M')}")
top_pos = stats_df.sort_values(by="Trefferquote (%)", ascending=False).iloc[0]
col4.metric("Bester Trefferpunkt", f"Position {int(top_pos['Position'])}", f"{top_pos['Trefferquote (%)']}% Trefferquote")

st.markdown("---")

# Interaktives Balkendiagramm
st.subheader("📊 Wahrscheinlichkeitsverteilung über den Zyklus")
fig = px.bar(
    stats_df,
    x="Position",
    y="Trefferquote (%)",
    text="Trefferquote (%)",
    labels={"Position": f"Kerzenposition im Zyklus (0 bis {cycle_length - 1})", "Trefferquote (%)": "Trendwende-Wahrscheinlichkeit (%)"},
    title=f"Trendwende-Häufigkeit je Zyklusposition ({selected_coin} / {tf_choice} – Start: {df_cycles.index[0].strftime('%d.%m.%Y %H:%M UTC')})"
)
fig.update_traces(
    marker_color='#089981',
    texttemplate='%{text:.1f}%',
    textposition='outside'
)
fig.update_layout(
    yaxis=dict(range=[0, 110]),
    xaxis=dict(tickmode='linear', dtick=1),
    template="plotly_dark",
    height=450
)
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# Tabellenübersicht
c_left, c_right = st.columns([1, 1])

with c_left:
    st.subheader("🏆 Rangliste nach Wahrscheinlichkeit")
    ranked_df = stats_df.sort_values(by="Trefferquote (%)", ascending=False).reset_index(drop=True)
    st.dataframe(
        ranked_df,
        column_config={
            "Position": st.column_config.NumberColumn("Position im Zyklus", format="%d"),
            "Trefferquote (%)": st.column_config.ProgressColumn(
                "Wahrscheinlichkeit",
                format="%.1f%%",
                min_value=0,
                max_value=100
            ),
        },
        use_container_width=True,
        hide_index=True
    )

with c_right:
    st.subheader("🔍 Detail-Matrix (Zyklus vs. Position)")
    st.caption("Ein Haken (✅) markiert, in welchem Zyklus an welcher Position eine Trendwende registriert wurde.")
    
    pivot_table = pd.crosstab(
        index=df_cycles['Cycle_ID'],
        columns=df_cycles['Position'],
        values=df_cycles['has_turn'],
        aggfunc=lambda x: "✅" if any(x) else "—"
    ).fillna("—")
    
    pivot_table.index.name = "Zyklus #"
    st.dataframe(pivot_table, use_container_width=True)
