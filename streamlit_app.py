import streamlit as st
from google.cloud import firestore_v1
import os
import json
import threading
import queue
import time # For simulating initial data load

# --- Configuration ---
# IMPORTANT: Replace with your actual project ID and collection paths.
# For local development, ensure GOOGLE_APPLICATION_CREDENTIALS environment variable
# points to your service account key file.
# For deployment, follow Streamlit's guide for secrets management or
# your hosting platform's method for setting environment variables.
GOOGLE_CLOUD_PROJECT_ID = "infiniquant-da402" # e.g., "my-quant-project-12345"
FIRESTORE_APP_ID = "1:608512799755:web:def0b365b005ef6166c30e" # A chosen identifier for your app within Firestore
FIRESTORE_COLLECTION_NAME = "quant_strategies" # The name of your collection for strategies

# --- Firestore Client Initialization (Cached) ---
@st.cache_resource
def get_firestore_client():
    """Initializes and returns a Firestore client.
    
    Expects GOOGLE_APPLICATION_CREDENTIALS to be set to the path of your
    service account key JSON file.
    """
    try:
        # Check if running in a Streamlit Cloud environment or if credentials are explicitly set
        if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ and "gcp_service_account" in st.secrets:
            # Use Streamlit secrets for service account credentials if available
            st.warning("Using Streamlit secrets for GCP service account. Ensure 'gcp_service_account' is configured.")
            
            # Create a temporary file for the service account key
            secrets_path = os.path.join(os.getcwd(), ".streamlit", "gcp_service_account.json")
            os.makedirs(os.path.dirname(secrets_path), exist_ok=True)
            
            with open(secrets_path, "w") as f:
                json.dump(st.secrets["gcp_service_account"], f)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = secrets_path
        
        elif "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
            st.error(
                "Environment variable GOOGLE_APPLICATION_CREDENTIALS not set. "
                "Please set it to the path of your Firestore service account key JSON file, "
                "or configure 'gcp_service_account' in Streamlit secrets."
            )
            st.stop() # Stop the app if credentials are not found
        
        db = firestore_v1.Client(project=GOOGLE_CLOUD_PROJECT_ID)
        st.success("Successfully initialized Firestore client.")
        return db
    except Exception as e:
        st.error(f"Error initializing Firestore: {e}")
        st.stop() # Stop the app if initialization fails

# --- Global Queue for Real-time Updates ---
# This queue will hold data pushed from the Firestore listener's background thread.
# Use st.cache_resource to ensure it's a singleton across reruns.
@st.cache_resource
def get_update_queue():
    return queue.Queue()

# --- Firestore Real-time Listener Callback ---
def on_snapshot(col_snapshot, changes, read_time):
    """Callback function for Firestore real-time listener."""
    current_data = []
    for doc in col_snapshot.documents:
        doc_data = doc.to_dict()
        if doc_data: # Ensure document has data
            doc_data['id'] = doc.id # Add document ID
            current_data.append(doc_data)
    
    # Put the entire current dataset into the queue.
    # This ensures we always have the latest state, rather than just changes.
    update_queue.put(current_data)
    st.session_state['data_updated'] = True # Signal that new data is available

# --- Setup Firestore Listener in a Background Thread ---
@st.cache_resource(hash_funcs={threading.Thread: lambda _: None})
def setup_firestore_listener(db_client, data_q):
    """Sets up the Firestore real-time listener in a separate thread.
    
    Returns the collection_watch object to allow detaching the listener if needed.
    """
    collection_path = f"artifacts/{FIRESTORE_APP_ID}/public/data/{FIRESTORE_COLLECTION_NAME}"
    try:
        collection_ref = db_client.collection(collection_path)
        
        # Start the listener in a background thread
        collection_watch = collection_ref.on_snapshot(on_snapshot)
        st.success(f"Listening for updates on collection: {collection_path}")
        return collection_watch
    except Exception as e:
        st.error(f"Error setting up Firestore listener: {e}")
        st.stop()

# --- Streamlit Application ---
st.set_page_config(layout="wide", page_title="Quant Strategy Dashboard")

st.title("📊 Pre-validated Quant Strategies")

# Get Firestore client and update queue
db = get_firestore_client()
update_queue = get_update_queue()

# Initialize session state for data storage and selected strategy type
if 'strategies_data' not in st.session_state:
    st.session_state['strategies_data'] = []
if 'selected_strategy_type' not in st.session_state:
    st.session_state['selected_strategy_type'] = "All"
if 'data_updated' not in st.session_state:
    st.session_state['data_updated'] = False


# Start the Firestore listener (only once)
if 'firestore_listener_started' not in st.session_state:
    with st.spinner("Connecting to Firestore and fetching initial data..."):
        # We need to explicitly call the setup function to ensure it runs
        # outside the initial Streamlit script execution, typically on app start.
        # The `on_snapshot` will populate the queue.
        setup_firestore_firestore_listener = setup_firestore_listener(db, update_queue)
        st.session_state['firestore_listener_started'] = True
        
        # Simulate waiting for initial data to arrive in the queue
        # In a real app, you might have a more sophisticated loading state
        # or fetch initial data synchronously.
        time.sleep(2) # Give a moment for the initial snapshot to arrive

# --- Process Updates from the Queue ---
# Check the queue at the beginning of each Streamlit rerun
if not update_queue.empty():
    with st.spinner("New data arrived! Updating strategies..."):
        latest_data = update_queue.get()
        st.session_state['strategies_data'] = latest_data
        st.session_state['data_updated'] = False # Reset signal

# --- UI for Filtering ---
all_strategy_types = ["All"] + sorted(list(set(
    s.get("Strategy_Type") for s in st.session_state['strategies_data'] if s.get("Strategy_Type")
)))

selected_type = st.selectbox(
    "Select Strategy Type:",
    options=all_strategy_types,
    key="strategy_type_selector",
    index=all_strategy_types.index(st.session_state['selected_strategy_type']) if st.session_state['selected_strategy_type'] in all_strategy_types else 0
)

# Update session state if selection changes
if selected_type != st.session_state['selected_strategy_type']:
    st.session_state['selected_strategy_type'] = selected_type
    st.rerun() # Rerun to apply filter immediately

# --- Display Strategies ---
st.subheader("Available Strategies")

filtered_strategies = []
if selected_type == "All":
    filtered_strategies = st.session_state['strategies_data']
else:
    filtered_strategies = [
        s for s in st.session_state['strategies_data'] 
        if s.get("Strategy_Type") == selected_type
    ]

if not filtered_strategies:
    st.info("No strategies found for the selected type, or no data available yet.")
else:
    # Sort strategies for consistent display
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
st.write("Please ensure your Firestore database contains a collection named `quant_strategies` under the path `artifacts/streamlit_quant_app/public/data/` with documents having fields like `Strategy_Name`, `Strategy_Type`, `Description`, `Performance_Metrics`, `Risk_Level`, `Recommended_Capital`, `Last_Updated`.")

# You can uncomment this line to force a rerun, but be cautious as it will
# trigger continuous reruns if data is constantly being pushed.
# if st.session_state['data_updated']:
#     st.rerun()
