"""Command center — VISUAL MOCKUP ONLY. Nothing here is wired up.

    streamlit run command_center/mockup.py

Every number below is hardcoded. This exists to settle the layout before any
of it gets built: what the command center should show, and roughly how. No
data is pulled, no config is read, no file is written.

Real version would read the parquet cache and config/settings.yaml.
"""

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Tracer — mockup", page_icon="📡", layout="wide")

# ---------------------------------------------------------------- fake data
CACHE = pd.DataFrame([
    ("GLD",  "ibkr", "2010-01-04", "2026-09-19", 4203, 0, "—"),
    ("GDX",  "ibkr", "2010-01-04", "2026-09-19", 4203, 0, "—"),
    ("SLV",  "ibkr", "2010-01-04", "2026-09-19", 4203, 0, "—"),
    ("GDXJ", "ibkr", "2010-01-04", "2026-09-19", 4203, 0, "short history"),
    ("XOP",  "wrds", "2010-01-04", "2026-08-29", 4187, 21, "—"),
    ("USO",  "wrds", "2010-01-04", "2026-08-29", 4187, 21, "—"),
    ("FXE",  "yfinance", "2010-01-04", "2026-09-19", 4201, 0, "last-resort source"),
], columns=["symbol", "source", "start", "end", "rows", "stale_days", "notes"])

HEALTH = {"ibkr": "up", "wrds": "up", "yfinance": "down"}

STRATEGIES = pd.DataFrame([
    ("ROME", "ROME", "dev", True, "ETF pairs trading across commodity, rates, credit and FX."),
    ("OSLO", "OSLO", "off", False, "(placeholder — not built)"),
], columns=["name", "universe", "status", "enabled", "description"])

# ---------------------------------------------------------------- layout
st.title("📡 Project Tracer — command center")
st.warning("**Mockup.** Every value on this page is hardcoded. Nothing is connected.", icon="⚠️")

page = st.sidebar.radio("Page", ["Data pipeline", "Strategies"])
st.sidebar.divider()
st.sidebar.caption("Mockup — no live data")

if page == "Data pipeline":
    st.header("Data pipeline")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Symbols cached", "42 / 42")
    c2.metric("Stale (>5d)", "2")
    c3.metric("Flagged", "1")
    c4.metric("Last full pull", "2h ago")

    st.subheader("Provider health")
    for column, (name, state) in zip(st.columns(3), HEALTH.items()):
        column.metric(name, state)

    st.subheader("Source mix — ROME")
    left, right = st.columns([2, 1])
    mix = pd.DataFrame({"symbols": [33, 7, 2]}, index=["ibkr", "wrds", "yfinance"])
    left.bar_chart(mix)
    right.dataframe(mix, width="stretch")
    right.caption("Each symbol comes from exactly one source.")

    st.subheader("Cache")
    st.dataframe(CACHE, hide_index=True, width="stretch")

    st.subheader("Recent log")
    st.code(
        "WARNING  [data_pulling] ibkr failed for XOP (reason: no security definition)\n"
        "                        → switched to wrds\n"
        "WARNING  [data_pulling] using yfinance for FXE — last-resort source\n"
        "INFO     [data_pulling] ROME pull complete: 42 symbols, 176,526 rows",
        language="text",
    )

else:
    st.header("Strategies")
    st.dataframe(STRATEGIES, hide_index=True, width="stretch")
    st.caption("Would read the `strategies:` block in config/settings.yaml.")

    for row in STRATEGIES.itertuples(index=False):
        with st.expander(f"{row.name} — {row.status}"):
            st.write(row.description)
            st.write(f"Universe: `{row.universe}` · Code: `programs/{row.name}/`")
            st.selectbox("Status", ["dev", "paper", "live", "off"],
                         index=["dev", "paper", "live", "off"].index(row.status),
                         key=row.name, disabled=True)
            st.caption("Disabled — mockup.")
