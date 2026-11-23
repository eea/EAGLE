"""A shared password for hosted deployments (e.g. render.com).

Set the environment variable ``APP_PASSWORD`` to switch it on. Without it the app is open,
so local runs and tests need nothing. There is deliberately no default password: a
hard-coded fallback would let anyone in who has read the source.
"""

import hmac
import os
import time

import streamlit as st

PASSWORD_VARIABLE = "APP_PASSWORD"
_OK = "password_correct"


def password_required() -> bool:
    return bool(os.environ.get(PASSWORD_VARIABLE))


def check_password() -> bool:
    """True once the visitor has entered the password (or none is required); otherwise shows the form."""
    expected = os.environ.get(PASSWORD_VARIABLE)
    if not expected or st.session_state.get(_OK):
        return True

    def entered():
        given = st.session_state.get("password", "")
        st.session_state["password"] = ""  # never keep the password in the session
        ok = hmac.compare_digest(given.encode(), expected.encode())
        st.session_state[_OK] = ok
        if not ok:
            time.sleep(1)  # slows down guessing

    st.title("🦅 EAGLE Eye", anchor=False)
    with st.form("login"):
        st.text_input("Password", type="password", key="password")
        st.form_submit_button("Enter", on_click=entered)
    if st.session_state.get(_OK) is False:
        st.error("Wrong password.")
    return False
