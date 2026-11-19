import time

import requests
import streamlit as st

from config import API_BASE_URL


def wait_for_backend(max_wait_seconds=90):
    """Wait until the API answers /health. Shows a message while the free instance wakes up."""
    if st.session_state.get("backend_ready"):
        return

    placeholder = st.empty()
    start = time.time()

    while time.time() - start < max_wait_seconds:
        try:
            r = requests.get(f"{API_BASE_URL}/health", timeout=10)
            if r.status_code == 200:
                placeholder.empty()
                st.session_state["backend_ready"] = True
                return
        except requests.RequestException:
            pass

        elapsed = int(time.time() - start)
        placeholder.info(
            f"Please wait a moment. We're on a free hosting plan, so the backend "
            f"may take up to a minute to wake up. ({elapsed}s)"
        )
        time.sleep(3)

    placeholder.error(
        "The backend is not responding yet. Please wait a minute and refresh the page."
    )
    st.stop()