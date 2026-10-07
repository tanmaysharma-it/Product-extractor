"""Email/password login using Supabase Auth."""
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

MIN_PASSWORD_LEN = 6  # Supabase default minimum


def _get_setting(name: str):
    """Read from .env / environment first, then Streamlit Cloud secrets."""
    value = os.getenv(name)
    if value:
        return value
    try:
        return st.secrets[name]
    except Exception:
        return None


def _client():
    """One Supabase client per browser session (so users never share a login)."""
    if "sb" not in st.session_state:
        url = _get_setting("SUPABASE_URL")
        key = _get_setting("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL / SUPABASE_KEY missing. Add them to your .env file.")
        from supabase import create_client

        st.session_state["sb"] = create_client(url, key)
    return st.session_state["sb"]


def is_enabled() -> bool:
    """Supabase login is only used when its keys are configured."""
    return bool(_get_setting("SUPABASE_URL") and _get_setting("SUPABASE_KEY"))


def passes_shared_password() -> bool:
    """Optional single shared password (set APP_PASSWORD). No password set -> app is open."""
    expected = _get_setting("APP_PASSWORD")
    if not expected or st.session_state.get("pw_ok"):
        return True
    st.title("Product Label Data Extractor")
    with st.form("pw_form"):
        pw = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Enter", type="primary")
    if submitted:
        if pw == expected:
            st.session_state["pw_ok"] = True
            st.rerun()
        else:
            st.error("Wrong password.")
    return False


def current_user():
    return st.session_state.get("user")


def sign_up(email: str, password: str) -> tuple[bool, str]:
    if not email or "@" not in email:
        return False, "Please enter a valid email."
    if len(password) < MIN_PASSWORD_LEN:
        return False, f"Password must be at least {MIN_PASSWORD_LEN} characters."
    try:
        res = _client().auth.sign_up({"email": email, "password": password})
    except Exception as e:
        return False, f"Sign up failed: {e}"

    if res.session and res.user:  # email confirmation is OFF -> logged in right away
        st.session_state["user"] = {"id": res.user.id, "email": res.user.email}
        return True, "Account created."
    return True, "Account created. Check your email to confirm it, then log in."


def sign_in(email: str, password: str) -> tuple[bool, str]:
    if not email or not password:
        return False, "Enter email and password."
    try:
        res = _client().auth.sign_in_with_password({"email": email, "password": password})
    except Exception as e:
        return False, f"Login failed: {e}"
    if not res.user:
        return False, "Login failed. Please try again."
    st.session_state["user"] = {"id": res.user.id, "email": res.user.email}
    return True, "Logged in."


def sign_out():
    try:
        _client().auth.sign_out()
    except Exception:
        pass
    for key in ("user", "sb", "df", "source"):
        st.session_state.pop(key, None)
    st.rerun()


def render_auth_page():
    """Login / Sign up screen. Call st.stop() after this if the user is not logged in."""
    st.title("Product Label Data Extractor")
    st.write("Please log in or create an account to continue.")

    try:
        _client()
    except RuntimeError as e:
        st.error(str(e))
        return

    login_tab, signup_tab = st.tabs(["Login", "Sign up"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Login", type="primary")
        if submitted:
            ok, msg = sign_in(email.strip(), password)
            if ok:
                st.rerun()
            else:
                st.error(msg)

    with signup_tab:
        with st.form("signup_form"):
            email = st.text_input("Email", key="signup_email")
            password = st.text_input(
                "Password", type="password", key="signup_password",
                help=f"At least {MIN_PASSWORD_LEN} characters",
            )
            submitted = st.form_submit_button("Create account", type="primary")
        if submitted:
            ok, msg = sign_up(email.strip(), password)
            if ok and current_user():
                st.rerun()
            elif ok:
                st.success(msg)
            else:
                st.error(msg)


def render_sidebar_account(user: dict):
    with st.sidebar:
        st.caption("Logged in as")
        st.write(user["email"])
        if st.button("Logout"):
            sign_out()