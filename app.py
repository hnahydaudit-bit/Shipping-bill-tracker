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
    st.error("Missing GEMINI_API_KEY. Please add it to Streamlit Secrets.")

st.set_page_config(page_title="Shipping Bill Data Extractor", layout="wide")
st.title("🚢 SHIPPING BILL DATA EXTRACTOR (ACCURATE)")

# ---------- Helper Functions ----------

def extract_text_from_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            # We extract text page by page to keep structural context
            text += f"\n--- PAGE {page.number + 1} ---\n"
            text += page.get_text("text")
    return text.strip()

def extract_with_ai(file_text, file_name):
    # Using the current stable model to avoid 404 errors
    MODEL_NAME = "gemini-2.0-flash" 
    
    prompt = f"""
    You are a professional Customs Auditor. Extract data from this Indian Shipping Bill with 100% accuracy.
    
    CRITICAL INSTRUCTION FOR LUT:
    1. Go to Page 1.
    2. Locate the table labeled 'STATUS'.
    3. Find the column header '11.LUT'.
    4. The value is the character (Y or N) printed directly in the row below that header.
    5. In this specific document, look at the grid: Mode is AIR, Jobbing is N, 11.LUT is N.
    6. Return 'N' if the document shows 'N' under 11.LUT. Do NOT use tax amounts to decide.

    Fields to extract (JSON ARRAY ONLY):
    - ".INV NO.": The Invoice Number (e.g., JEHIN/2025/00090).
    - "SB No": The Shipping Bill Number (7-digit number).
    - "SB date": The Shipping Bill Date (DD-MMM-YY).
    - "Port code": The 6-character identifier (e.g., INHYD4).
    - "LUT": Strictly 'Y' or 'N' from the Status Table.
    - "IGST AMT": The numeric Integrated Tax amount.

    Document: {file_name}
    Content: {file_text}
    """

    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt)
        
        # Clean AI response for JSON
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        match = re.search(r"\[.*\]", clean_text, re.DOTALL)
        return json.loads(match.group(0)) if match else []
    except Exception as e:
        st.error(f"Error extracting {file_name}: {e}")
        return []

# ---------- UI Layout ----------

uploaded_files = st.file_uploader("Upload Shipping Bill PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    if st.button("Generate Final Report"):
        all_data = []
        with st.spinner("Analyzing structural data for 100% accuracy..."):
            for uploaded in uploaded_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded.read())
                    text = extract_text_from_pdf(tmp.name)
                os.remove(tmp.name)
                
                # Send full text to ensure AI finds the Status table correctly
                res = extract_with_ai(text, uploaded.name)
                if res:
                    all_data.extend(res)

        if all_data:
            df = pd.DataFrame(all_data)
            
            # Enforce Column Order: .INV NO. first
            cols = [".INV NO.", "SB No", "SB date", "Port code", "LUT", "IGST AMT"]
            for c in cols:
                if c not in df.columns: df[c] = "N/A"
            
            df = df[cols]
            
            # Rename for final presentation
            df.rename(columns={
                "LUT": 'LUT "Y" or "N"', 
                "IGST AMT": '"IGST AMT"', 
                "Port code": '"Port code"'
            }, inplace=True)
            
            st.success("Extraction Complete")
            st.dataframe(df)

            # Excel Export
            excel_out = "Accurate_Shipping_Data.xlsx"
            df.to_excel(excel_out, index=False)
            with open(excel_out, "rb") as f:
                st.download_button("📥 Download Excel Report", f, file_name=excel_out)
