import streamlit as st

st.set_page_config(page_title="Mirror", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
#MainMenu, header, footer {visibility:hidden;}
.block-container {padding:0 !important; margin:0 !important; max-width:100% !important;}
html, body {margin:0 !important; padding:0 !important; overflow:hidden;}
body {background:transparent !important;}
</style>
""", unsafe_allow_html=True)

# بدّل هذا بالسطر الفعلي بعد تفعيل Pages:
GH_PAGES_URL = "https://<USERNAME>.github.io/<REPO>/"

st.components.v1.iframe(GH_PAGES_URL, height=3600, scrolling=True)
st.markdown(f"[فتح الصفحة كاملة ↗]({GH_PAGES_URL})")
