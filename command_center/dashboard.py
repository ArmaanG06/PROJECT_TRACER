"""Read-only Streamlit dashboard. Launched by `tracer dashboard`.

Observation only: it reads the cache, the universe files and the strategy
registry. Nothing here writes, and nothing touches execution.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from data_pulling import get_settings, list_universes, load_universe, store
from data_pulling.providers import PROVIDER_ORDER, get_provider, reset_providers

from command_center.registry import load_registry, registry_path

st.set_page_config(page_title="Project Tracer", page_icon="📡", layout="wide")


@st.cache_data(ttl=30)
def cached_status() -> pd.DataFrame:
    return store.status()


def page_data() -> None:
    st.header("Data pipeline")
    manifest = cached_status()

    if manifest.empty:
        st.warning("Cache is empty. Run `tracer data pull --universe ROME`.")
    else:
        columns = st.columns(3)
        columns[0].metric("Series cached", len(manifest))
        columns[1].metric("Symbols", manifest["symbol"].nunique())
        columns[2].metric("Stale (>5d)", int((manifest["stale_days"] > 5).sum()))

    st.subheader("Provider health")
    if st.button("Run healthcheck"):
        results = {}
        for name in PROVIDER_ORDER:
            try:
                results[name] = get_provider(name).healthcheck()
            except Exception:
                results[name] = False
        reset_providers()
        for column, (name, ok) in zip(st.columns(len(results)), results.items()):
            column.metric(name, "up" if ok else "down")
    else:
        st.caption("Healthchecks open live connections, so they run on demand.")

    if not manifest.empty:
        st.subheader("Source mix per universe")
        universes = list_universes()
        if universes:
            selected = st.selectbox("Universe", universes)
            symbols = set(load_universe(selected)["symbol"])
            scoped = manifest[manifest["symbol"].isin(symbols)]
            if scoped.empty:
                st.info(f"Nothing cached for {selected}.")
            else:
                mix = scoped.groupby("source")["symbol"].nunique().rename("symbols").reset_index()
                left, right = st.columns([1, 2])
                left.dataframe(mix, hide_index=True, width="stretch")
                right.bar_chart(mix.set_index("source"))
                missing = sorted(symbols - set(scoped["symbol"]))
                if missing:
                    st.warning(f"Not cached: {', '.join(missing)}")

        st.subheader("Cache")
        st.dataframe(
            manifest.sort_values(["stale_days", "symbol"], ascending=[False, True]),
            hide_index=True,
            width="stretch",
        )


def page_strategies() -> None:
    st.header("Strategies")
    try:
        registry = load_registry()
    except FileNotFoundError as exc:
        st.error(str(exc))
        return

    st.dataframe(
        pd.DataFrame([vars(s) for s in registry.values()]), hide_index=True, width="stretch"
    )
    st.caption(f"Read-only view of {registry_path()} — edit with `tracer algo set`.")

    for strategy in registry.values():
        with st.expander(f"{strategy.name} — {strategy.status}"):
            st.write(strategy.description or "_No description._")
            try:
                st.dataframe(load_universe(strategy.universe), hide_index=True, width="stretch")
            except FileNotFoundError:
                st.warning(f"No universe file for {strategy.universe}.")


st.title("📡 Project Tracer")
st.caption("Read-only. No order entry, no positions, nothing that touches execution.")

page = st.sidebar.radio("Page", ["Data pipeline", "Strategies"])
st.sidebar.caption(f"Root: `{get_settings().root}`")

if page == "Data pipeline":
    page_data()
else:
    page_strategies()
