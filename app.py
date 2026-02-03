import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import google.generativeai as genai
import tempfile
import os
import json
import re

# 🔑 Configure Gemini
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Missing GEMINI_API_KEY in Streamlit Secrets.")

st.set_page_config(page_title="SHIPPING BILL EXTRACTOR", page_icon="🚢", layout="wide")
st.title("🚢 SHIPPING BILL DATA EXTRACTOR")

# ---------- Helper Functions ----------

def extract_text_from_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text("text")
    return text.strip()

def extract_shipping_details_with_ai(batch_texts):
    # Using the latest Gemini 2.0 Flash model to avoid 404/deprecated errors
    # If this fails, try "gemini-1.5-flash" or "gemini-1.5-pro"
    MODEL_NAME = "gemini-2.0-flash" 
    
    prompt = f"""
    Act as a customs data entry expert. Extract from these Indian Shipping Bills:
    1. SB No
    2. SB date
    3. LUT "Y" or "N" (Look at the status table; mark Y if under LUT)
    4. "IGST AMT" (Numerical value only)
    5. "Port code" (6-character code like INHYD4)

    Return a JSON ARRAY. If a value is missing, return null.
    Documents: {json.dumps(batch_texts)}
    """

    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt)
        
        # Clean response and extract JSON
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        match = re.search(r"\[.*\]", clean_text, re.DOTALL)
        return json.loads(match.group(0)) if match else []
    except Exception as e:
        st.error(f"Extraction Error: {str(e)}")
        return []

# ---------- Streamlit UI ----------

with st.sidebar:
    st.header("Debug Tools")
    if st.button("Check Available Models"):
        try:
            models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            st.write("Available models for your key:")
            st.json(models)
        except Exception as e:
            st.error(f"Could not list models: {e}")

uploaded_files = st.file_uploader("Upload Shipping Bill PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    if st.button("Process All Files"):
        batch_data = []
        for uploaded in uploaded_files:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded.read())
                text = extract_text_from_pdf(tmp.name)
            os.remove(tmp.name)
            batch_data.append({"Source": uploaded.name, "Text": text[:15000]})

        with st.spinner("AI is reading your bills..."):
            results = extract_shipping_details_with_ai(batch_data)

        if results:
            df = pd.DataFrame(results)
            # Match the exact column names requested by the user
            mapping = {
                "SB No": "SB No",
                "SB date": "SB date",
                "LUT \"Y\" or \"N\"": 'LUT "Y" or "N"',
                "IGST AMT": '"IGST AMT"',
                "Port code": '"Port code"'
            }
            df.rename(columns=mapping, inplace=True)
            
            st.success("Extraction Complete")
            st.dataframe(df)

            # Export to Excel
            out_path = "Shipping_Bill_Data.xlsx"
            df.to_excel(out_path, index=False)
            with open(out_path, "rb") as f:
                st.download_button("📥 Download Excel", f, file_name="Shipping_Bill_Data.xlsx")
        else:
            st.error("AI could not find the data. Try checking the 'Available Models' in the sidebar.")
