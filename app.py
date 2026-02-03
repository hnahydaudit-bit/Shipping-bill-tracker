import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import google.generativeai as genai
import tempfile
import os
import json
import re

# 1. 🔑 CONFIGURATION (Stable 2026 Setup)
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Missing API Key. Add 'GEMINI_API_KEY' to Streamlit Secrets.")

st.set_page_config(page_title="Customs Data Extractor", layout="wide")
st.title("🚢 SHIPPING BILL DATA EXTRACTOR")

# 2. 🧠 CORE AI EXTRACTION (Updated to Gemini 2.5 Flash)
def extract_with_ai(file_text, file_name):
    # Using the current stable 2026 model to avoid 404 errors
    MODEL_NAME = "gemini-2.5-flash" 
    
    prompt = f"""
    Return a JSON ARRAY for this Shipping Bill. 
    ACCURACY IS CRITICAL.
    
    1. ".INV NO.": Find the Invoice Number (often near the top or in Part III).
    2. "SB No": The Shipping Bill Number.
    3. "SB date": The Shipping Bill Date (DD-MMM-YY).
    4. "Port code": The 6-character port identifier (e.g., INHYD4).
    5. "LUT": Strictly 'Y' if '11.LUT' in the Status table shows 'Y'. 
       If it shows 'N', return 'N'. Do not guess based on taxes.
    6. "IGST AMT": The total Integrated Tax amount (numeric only).
    
    Document Context: {file_name}
    Content: {file_text[:15000]}
    """

    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt)
        
        # Robust JSON cleaning
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        match = re.search(r"\[.*\]", clean_text, re.DOTALL)
        return json.loads(match.group(0)) if match else []
    except Exception as e:
        if "404" in str(e):
            st.warning(f"Model {MODEL_NAME} not found. Trying fallback model...")
            # Fallback to general latest alias
            model = genai.GenerativeModel("gemini-flash-latest")
            return json.loads(re.search(r"\[.*\]", model.generate_content(prompt).text, re.DOTALL).group(0))
        elif "429" in str(e):
            st.error("🚨 QUOTA ERROR: Your key has 'Limit 0'. You MUST link a billing account in Google AI Studio Settings to activate your free quota.")
        return []

# 3. 📂 FILE PROCESSING
uploaded_files = st.file_uploader("Upload Shipping Bill PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_files and st.button("🚀 Process & Generate Excel"):
    final_rows = []
    for uploaded in uploaded_files:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded.read())
            doc = fitz.open(tmp.name)
            text = "".join([page.get_text() for page in doc])
            doc.close()
        os.remove(tmp.name)
        
        data = extract_with_ai(text, uploaded.name)
        if data: final_rows.extend(data)

    if final_rows:
        df = pd.DataFrame(final_rows)
        
        # Enforce exact column order and labels requested
        cols = [".INV NO.", "SB No", "SB date", "LUT", "IGST AMT", "Port code"]
        for c in cols: 
            if c not in df.columns: df[c] = "N/A"
            
        df = df[cols]
        df.rename(columns={"LUT": 'LUT "Y" or "N"', "IGST AMT": '"IGST AMT"', "Port code": '"Port code"'}, inplace=True)
        
        st.success("Extraction Successful!")
        st.dataframe(df)
        
        # Direct Excel Download
        output = "Shipping_Bill_Data.xlsx"
        df.to_excel(output, index=False)
        with open(output, "rb") as f:
            st.download_button("📥 Download Excel Report", f, file_name=output)
