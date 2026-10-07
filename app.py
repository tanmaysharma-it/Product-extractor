import streamlit as st

from auth import current_user, is_enabled, passes_shared_password, render_auth_page, render_sidebar_account
from extractor import ExtractionError, extract_products
from utils import group_pairs, prepare_image, records_to_dataframe, to_csv_bytes, to_excel_bytes

st.set_page_config(page_title="Product Label Data Extractor", page_icon="🏷️", layout="wide")

# --- Access gate: Supabase login if configured, else optional shared password, else open ---
if is_enabled():
    user = current_user()
    if user is None:
        render_auth_page()
        st.stop()
    render_sidebar_account(user)
elif not passes_shared_password():
    st.stop()

st.title("Product Label Data Extractor")
st.write(
    "Upload an image containing multiple product labels and extract "
    "Article Name, Size and MRP automatically."
)

uploaded = st.file_uploader("Upload image", type=["jpg", "jpeg", "png"])

if uploaded is None:
    st.info("Upload a JPG, JPEG or PNG image to begin.")
    st.stop()

# Validate image
try:
    jpeg_bytes, mime, pil_img = prepare_image(uploaded.getvalue())
except ValueError as e:
    st.error(str(e))
    st.stop()

st.image(pil_img, caption=uploaded.name, use_container_width=True)

if st.button("Extract Product Data", type="primary"):
    try:
        with st.spinner("Reading labels... this can take 10–40 seconds for crowded images."):
            records = extract_products(jpeg_bytes, mime)
        df = records_to_dataframe(records)
        if df.empty:
            st.warning("No product labels were detected. Try a clearer or closer photo.")
        st.session_state["df"] = df
        st.session_state["source"] = uploaded.name
    except ExtractionError as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"Unexpected error: {e}")

df = st.session_state.get("df")
if df is not None and not df.empty and st.session_state.get("source") == uploaded.name:
    st.subheader("Extracted Data")
    st.metric("Total products detected", len(df))
    st.caption("You can edit any cell, add rows, or delete rows before downloading.")

    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="editor",
    )

    nd = (edited == "Not Detected").sum().sum()
    if nd:
        st.warning(f"{nd} field(s) are marked 'Not Detected'. Please review them.")

    grouped_view = st.checkbox(
        "Group same Article Name + MRP as pairs",
        help="Rows with the same Article Name and MRP are merged: sizes are combined and Pairs shows the count.",
    )
    if grouped_view:
        export_df = group_pairs(edited)
        st.subheader("Grouped Data")
        st.dataframe(export_df, use_container_width=True, hide_index=True)
    else:
        export_df = edited

    c1, c2, _ = st.columns([1, 1, 4])
    c1.download_button("Download CSV", to_csv_bytes(export_df), "products.csv", "text/csv")
    c2.download_button(
        "Download Excel",
        to_excel_bytes(export_df),
        "products.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )