import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import plotly.express as px
from datetime import datetime, timezone, date, time as dt_time

# ----------------- Seiten-Konfiguration -----------------
st.set_page_config(page_title="PZP Auto-Phase Cycle Profiler", page_icon="🎯", layout="wide")

st.title("🎯 PZP Zyklus-Profiler mit Auto-Phase-Alignment")
st.caption("Findet automatisch den optimalen Zyklus-Startpunkt, an dem die meisten Trendwenden zusammenfallen.")

# US-kompatible Datenquelle (Kraken)
@st.cache_resource
def get_exchange():
    return ccxt.kraken({
        'enableRateLimit': True,
    })

exchange = get_exchange()

# Timeframe-Konfigurationen
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
    
    market_list = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK", "NEAR"]
    selected_coin = st.selectbox("Markt / Asset", options=market_list, index=0)
    
    tf_options = list(TF_CONFIG.keys())
    tf_choice = st.selectbox("Timeframe", options=tf_options, index=tf_options.index("1d"))
    
    st.markdown("---")
    st.subheader("🔁 Zyklus-Einstellungen")
    cycle_length = st.number_input("Zykluslänge N (in Kerzen)", min_value=3, max_value=120, value=4, step=1)
    cycle_count = st.number_input("Anzahl Zyklen zum Vergleichen", min_value=2, max_value=40, value=10, step=1)
    
    st.markdown("##### Basis-Startzeitpunkt")
    col_d, col_t = st.columns([1, 1])
    with col_d:
        start_date_input = st.date_input("Startdatum", value=date(2024, 1, 1))
    with col_t:
        start_time_input = st.time_input("Startuhrzeit (UTC)", value=dt_time(0, 0), step=300)
        
    auto_align = st.checkbox("🎯 Auto-Phase-Alignment (Besten Startpunkt finden)", value=True)
    manual_offset = 0
    if not auto_align:
        manual_offset = st.slider("Manueller Start-Offset (Kerzen)", 0, int(cycle_length - 1), 0)
        
    st.markdown("---")
    st.subheader("📐 PZP-Algorithmus Parameter")
    pL = st.number_input("Pivot Links (L)", min_value=1, value=2)
    pR = st.number_input("Pivot Rechts (R)", min_value=1, value=2)
    factor = st.number_input("Projektionsfaktor", min_value=0.05, value=0.5, step=0.05)
    
    st.button("🔄 Neu berechnen", use_container_width=True)

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
with st.spinner(f"Lade Kursdaten für {selected_coin}..."):
    df_raw = fetch_candles(selected_coin, tf_choice)

if df_raw is None or len(df_raw) < 50:
    st.error("Fehler beim Laden der Kursdaten.")
    st.stop()

df = identify_trend_changes(df_raw, pL, pR, factor)

start_dt = pd.to_datetime(datetime.combine(start_date_input, start_time_input)).tz_localize('UTC')
df_sub = df[df.index >= start_dt].copy()

if len(df_sub) < (cycle_count * cycle_length + cycle_length):
    available_cycles = (len(df_sub) - cycle_length) // cycle_length
    if available_cycles < 2:
        st.error(f"Zu wenige Kerzen ab Startzeitpunkt vorhanden. Bitte wähle ein früheres Startdatum.")
        st.stop()
    cycle_count = available_cycles

# ----------------- Phasen-Optimierung -----------------
# Testet alle Offsets (0 bis cycle_length - 1) durch
phase_eval = []

for offset in range(int(cycle_length)):
    # Zyklen ab Offset schneiden
    sub_slice = df_sub.iloc[offset : offset + cycle_count * cycle_length].copy()
    sub_slice['Position'] = [idx % cycle_length for idx in range(len(sub_slice))]
    sub_slice['Cycle_ID'] = [idx // cycle_length + 1 for idx in range(len(sub_slice))]
    
    # Berechne max. Trefferquote an einer Position
    max_hit_rate = 0.0
    best_pos = 0
    total_cluster_score = 0.0
    
    for pos in range(cycle_length):
        turns_at_pos = sub_slice[(sub_slice['Position'] == pos) & (sub_slice['has_turn'] == True)]
        hit_cycles = turns_at_pos['Cycle_ID'].nunique()
        pct = (hit_cycles / cycle_count) * 100
        total_cluster_score += pct**2  # Quadratische Gewichtung bevorzugt deutliche Spitzen
        if pct > max_hit_rate:
            max_hit_rate = pct
            best_pos = pos
            
    start_time_actual = sub_slice.index[0]
    phase_eval.append({
        "Offset (Kerzen)": offset,
        "Effektiver Start": start_time_actual.strftime("%d.%m.%y %H:%M"),
        "Spitzen-Trefferquote (%)": round(max_hit_rate, 1),
        "Beste Position": best_pos,
        "Score": total_cluster_score
    })

phase_df = pd.DataFrame(phase_eval)

# Besten Offset ermitteln
if auto_align:
    best_phase_row = phase_df.sort_values(by=["Spitzen-Trefferquote (%)", "Score"], ascending=False).iloc[0]
    chosen_offset = int(best_phase_row["Offset (Kerzen)"])
else:
    chosen_offset = manual_offset
    best_phase_row = phase_df[phase_df["Offset (Kerzen)"] == chosen_offset].iloc[0]

# ----------------- Finale Analyse mit gewähltem Offset -----------------
df_final = df_sub.iloc[chosen_offset : chosen_offset + cycle_count * cycle_length].copy()
df_final['Position'] = [idx % cycle_length for idx in range(len(df_final))]
df_final['Cycle_ID'] = [idx // cycle_length + 1 for idx in range(len(df_final))]

position_stats = []
for pos in range(cycle_length):
    turns_at_pos = df_final[(df_final['Position'] == pos) & (df_final['has_turn'] == True)]
    unique_cycles = turns_at_pos['Cycle_ID'].nunique()
    pct = round((unique_cycles / cycle_count) * 100, 1)
    position_stats.append({
        "Position": pos,
        "Trendwechsel (Zyklen)": f"{unique_cycles} / {cycle_count}",
        "Trefferquote (%)": pct
    })

stats_df = pd.DataFrame(position_stats)

# ----------------- UI Dashboard -----------------
if auto_align:
    st.success(f"🎯 **Bester Startpunkt gefunden:** Versatz um **+{chosen_offset} Kerzen** führt zu einer Spitzen-Trefferquote von **{best_phase_row['Spitzen-Trefferquote (%)']}%** auf Position **{int(best_phase_row['Beste Position'])}**!")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Gewählter Offset", f"+{chosen_offset} Kerzen")
col2.metric("Effektiver Zyklus 1 Start", f"{df_final.index[0].strftime('%d.%m.%y %H:%M')}")
col3.metric("Zykluslänge", f"{cycle_length} Kerzen ({tf_choice})")
top_res = stats_df.sort_values(by="Trefferquote (%)", ascending=False).iloc[0]
col4.metric("Höchste Konzentration", f"Pos {int(top_res['Position'])}", f"{top_res['Trefferquote (%)']}% Treffer")

st.markdown("---")

# Visualisierung
st.subheader("📊 Wahrscheinlichkeitsverteilung über den Zyklus")
fig = px.bar(
    stats_df,
    x="Position",
    y="Trefferquote (%)",
    text="Trefferquote (%)",
    labels={"Position": f"Kerzen-Index im Zyklus (0 bis {cycle_length - 1})", "Trefferquote (%)": "Wahrscheinlichkeit (%)"},
    title=f"Optimierte Zyklus-Verteilung ({selected_coin} / {tf_choice}) – Start: {df_final.index[0].strftime('%d.%m.%Y %H:%M UTC')}"
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
    height=420
)
st.plotly_chart(fig, use_container_width=True)

# Detailansicht & Phasenvergleich
tab1, tab2, tab3 = st.tabs(["🏆 Rangliste & Matrix", "🔬 Phasen-Vergleich (Alle Varianten)", "📅 Zyklus-Zeiten"])

with tab1:
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("##### Rangliste der Positionen")
        st.dataframe(
            stats_df.sort_values(by="Trefferquote (%)", ascending=False),
            column_config={
                "Position": st.column_config.NumberColumn("Position", format="%d"),
                "Trefferquote (%)": st.column_config.ProgressColumn("Trefferquote", format="%.1f%%", min_value=0, max_value=100)
            },
            use_container_width=True,
            hide_index=True
        )
    with c2:
        st.markdown("##### Treffer-Matrix je Zyklus")
        piv = pd.crosstab(
            index=df_final['Cycle_ID'],
            columns=df_final['Position'],
            values=df_final['has_turn'],
            aggfunc=lambda x: "✅" if any(x) else "—"
        ).fillna("—")
        piv.index.name = "Zyklus #"
        st.dataframe(piv, use_container_width=True)

with tab2:
    st.markdown("##### Vergleich aller getesteten Start-Offsets")
    st.caption("Das System hat alle Versatz-Möglichkeiten durchgerechnet. Der hervorgehobene Offset liefert die stärkste Bündelung:")
    st.dataframe(
        phase_df.drop(columns=["Score"]),
        column_config={
            "Spitzen-Trefferquote (%)": st.column_config.ProgressColumn("Spitzen-Trefferquote", format="%.1f%%", min_value=0, max_value=100),
            "Offset (Kerzen)": st.column_config.NumberColumn("Verschiebung", format="%d")
        },
        use_container_width=True,
        hide_index=True
    )

with tab3:
    st.markdown("##### Start- und Endzeitpunkte der Zyklen")
    cycle_times = []
    for cid in range(1, cycle_count + 1):
        c_sub = df_final[df_final['Cycle_ID'] == cid]
        cycle_times.append({
            "Zyklus #": cid,
            "Start": c_sub.index[0].strftime("%d.%m.%Y %H:%M"),
            "Ende": c_sub.index[-1].strftime("%d.%m.%Y %H:%M")
        })
    st.dataframe(pd.DataFrame(cycle_times), use_container_width=True, hide_index=True)
