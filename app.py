import streamlit as st
import pandas as pd
import fitz
import google.generativeai as genai
import tempfile
import os
import json
import re

# 🔑 Configure Gemini
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Add your GEMINI_API_KEY to Streamlit Secrets.")

st.set_page_config(page_title="Shipping Bill Extractor", layout="wide")
st.title("🚢 SHIPPING BILL EXTRACTOR")

# ---------- Model Selector (Side bar) ----------
with st.sidebar:
    st.header("Settings")
    # gemini-1.5-flash-lite usually has the highest free daily quota
    selected_model = st.selectbox(
        "Select AI Model (Switch if you get Quota Error)",
        ["gemini-1.5-flash-lite", "gemini-1.5-flash", "gemini-2.0-flash"],
        index=0
    )
    st.info("💡 If you get a '429 Quota Exceeded' error, try switching to 'flash-lite' or wait a few minutes.")

# ---------- Helper Functions ----------
def extract_text_from_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text("text")
    return text.strip()

def extract_with_ai(batch_texts, model_name):
    prompt = f"""
    Return a JSON ARRAY. Fields: "SB No", "SB date", "LUT", "IGST AMT", "Port code", "Source".
    LUT: 'Y' if under LUT/Bond, 'N' if IGST paid.
    Documents: {json.dumps(batch_texts)}
    """
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        
        # Simple JSON extraction
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        match = re.search(r"\[.*\]", clean_text, re.DOTALL)
        return json.loads(match.group(0)) if match else []
    except Exception as e:
        if "429" in str(e):
            st.error("🚨 Quota Exceeded! Please switch the model in the sidebar or add a billing account to your Google AI project.")
        else:
            st.error(f"Error: {e}")
        return []

# ---------- Main UI ----------
uploaded_files = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_files and st.button("Extract Data"):
    all_extracted_data = []
    
    for uploaded in uploaded_files:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded.read())
            text = extract_text_from_pdf(tmp.name)
        os.remove(tmp.name)
        
        # Process each file to minimize token count per request
        res = extract_with_ai([{"Source": uploaded.name, "Text": text[:10000]}], selected_model)
        if res:
            all_extracted_data.extend(res)

    if all_extracted_data:
        df = pd.DataFrame(all_extracted_data)
        # Rename columns to your specific requirement
        rename_map = {
            "SB No": "SB No", "SB date": "SB date", 
            "LUT": 'LUT "Y" or "N"', "IGST AMT": '"IGST AMT"', "Port code": '"Port code"'
        }
        df.rename(columns=rename_map, inplace=True)
        st.dataframe(df)
        
        # Excel Download
        df.to_excel("Export.xlsx", index=False)
        with open("Export.xlsx", "rb") as f:
            st.download_button("📥 Download Excel", f, file_name="Shipping_Bill_Data.xlsx")
