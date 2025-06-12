import streamlit as st
from google.cloud import firestore_v1
import os
import json
import threading
import queue
import time

GOOGLE_CLOUD_PROJECT_ID = "infiniquant-da402"
FIRESTORE_APP_ID = "1:608512799755:web:def0b365b005ef6166c30e"
FIRESTORE_COLLECTION_NAME = "quant_strategies"

@st.cache_resource
def get_firestore_client():
    try:
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"])
        )
        db = firestore_v1.Client(
            project=st.secrets["gcp_service_account"]["project_id"],
            credentials=credentials
        )
        st.success("Successfully initialized Firestore client.")
        return db
    except Exception as e:
        st.error(f"Error initializing Firestore: {e}")
        st.stop()

@st.cache_resource
def get_update_queue():
    return queue.Queue()

def on_snapshot(col_snapshot, changes, read_time):
    current_data = []
    for doc in col_snapshot.documents:
        doc_data = doc.to_dict()
        if doc_data:
            doc_data['id'] = doc.id
            current_data.append(doc_data)
    update_queue.put(current_data)
    st.session_state['data_updated'] = True

def setup_firestore_listener(db_client, data_q):
    collection_path = f"artifacts/{FIRESTORE_APP_ID}/public/data/{FIRESTORE_COLLECTION_NAME}"
    try:
        collection_ref = db_client.collection(collection_path)
        collection_watch = collection_ref.on_snapshot(on_snapshot)
        st.success(f"Listening for updates on collection: {collection_path}")
        return collection_watch
    except Exception as e:
        st.error(f"Error setting up Firestore listener: {e}")
        st.stop()

st.set_page_config(layout="wide", page_title="Quant Strategy Dashboard")
st.title("\U0001F4C8 Pre-validated Quant Strategies")

db = get_firestore_client()
update_queue = get_update_queue()

if 'strategies_data' not in st.session_state:
    st.session_state['strategies_data'] = []
if 'selected_strategy_type' not in st.session_state:
    st.session_state['selected_strategy_type'] = "All"
if 'data_updated' not in st.session_state:
    st.session_state['data_updated'] = False

if 'firestore_listener_started' not in st.session_state:
    with st.spinner("Connecting to Firestore and fetching initial data..."):
        setup_firestore_firestore_listener = setup_firestore_listener(db, update_queue)
        st.session_state['firestore_listener_started'] = True
        time.sleep(2)

if not update_queue.empty():
    with st.spinner("New data arrived! Updating strategies..."):
        latest_data = update_queue.get()
        st.session_state['strategies_data'] = latest_data
        st.session_state['data_updated'] = False

strategy_types_from_data = sorted(list(set(
    s.get("Strategy_Type") for s in st.session_state['strategies_data'] if s.get("Strategy_Type")
)))

base_strategies = ["RSI_ONLY", "MACD_ONLY", "SMA_CROSSOVER", "EMA_CROSSOVER", "BB_BOUNCE",
                   "RSI_SENTIMENT", "MACD_SENTIMENT", "SMA_SENTIMENT", "ML_PREDICT", 
                   "FF_INSPIRED_STRATEGY"]

quoted_base_strategies = [f'"{s}"' for s in base_strategies]
strategy_types_from_data = sorted(list(set(
    s.get("Strategy_Type") for s in st.session_state['strategies_data'] if s.get("Strategy_Type")
)))

all_strategy_types_set = list(dict.fromkeys(quoted_base_strategies + strategy_types_from_data))
selected = st.session_state.get('selected_strategy_type')
quoted_selected = f'"{selected}"' if selected and not selected.startswith('"') else selected

if quoted_selected in all_strategy_types_set:
    all_strategy_types = [quoted_selected] + [s for s in all_strategy_types_set if s != quoted_selected]
else:
    all_strategy_types = all_strategy_types_set

selected_type = st.selectbox(
    "Select Strategy Type:",
    options=all_strategy_types,
    key="strategy_type_selector",
    index=0
)

unquoted_selected_type = selected_type.strip('"')
if unquoted_selected_type != st.session_state.get('selected_strategy_type'):
    st.session_state['selected_strategy_type'] = unquoted_selected_type
    st.rerun()

# --- Add filters for key metrics ---
st.markdown("### \U0001F4C9 Filter by Performance Metrics")
min_sharpe = st.number_input("Minimum Sharpe Ratio", value=0.2)
min_profit_factor = st.number_input("Minimum Profit Factor", value=1.0)
min_sortino = st.number_input("Minimum Sortino Ratio", value=0.2)
min_total_return = st.number_input("Minimum Total Return (%)", value=1.0)

# --- Display Strategies ---
st.subheader("Available Strategies")

strategies = st.session_state['strategies_data']
if selected_type != "All":
    strategies = [s for s in strategies if s.get("Strategy_Type") == selected_type]

filtered_strategies = []
for s in strategies:
    perf = s.get("Performance_Metrics", {})
    try:
        sharpe = float(perf.get("Sharpe_Ratio", 0))
        pf = float(perf.get("Profit_Factor", 0))
        sortino = float(perf.get("Sortino_Ratio", 0))
        total_return = float(perf.get("Total_Return", 0)) * 100  # Convert to %
    except:
        continue

    if (
        sharpe >= min_sharpe and
        pf >= min_profit_factor and
        sortino >= min_sortino and
        total_return >= min_total_return
    ):
        filtered_strategies.append(s)

if not filtered_strategies:
    st.info("No strategies found for the selected filters or type.")
else:
    filtered_strategies_sorted = sorted(filtered_strategies, key=lambda x: x.get('Strategy_Name', ''))
    for strategy in filtered_strategies_sorted:
        with st.expander(f"**{strategy.get('Strategy_Name', 'N/A')}** - Type: {strategy.get('Strategy_Type', 'N/A')}"):
            st.write(f"**Description:** {strategy.get('Description', 'N/A')}")
            st.write(f"**Performance Metrics:**")
            metrics = strategy.get('Performance_Metrics', {})
            if metrics:
                for metric, value in metrics.items():
                    st.write(f"- {metric.replace('_', ' ').title()}: {value}")
            else:
                st.write("- No performance metrics available.")

            st.write(f"**Risk Level:** {strategy.get('Risk_Level', 'N/A')}")
            st.write(f"**Recommended Capital:** {strategy.get('Recommended_Capital', 'N/A')}")
            st.write(f"**Last Updated:** {strategy.get('Last_Updated', 'N/A')}")
            st.caption(f"Document ID: {strategy.get('id', 'N/A')}")

st.markdown("---")
st.write("Data last fetched from Firestore. New data will appear automatically (requires user interaction to trigger rerun).")
