"""Per-tab render modules for the PawPilot Streamlit UI.

Each module exposes a ``render()`` function that draws one tab's content.
``web.app`` wires them into ``st.tabs`` so this package owns all
scenario-specific UI while ``app.py`` stays a thin entry point.
"""
