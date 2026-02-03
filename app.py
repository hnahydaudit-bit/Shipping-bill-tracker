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

st.set_page_config(page_title="Shipping Bill Extractor", layout="wide")
st.title("🚢 SHIPPING BILL DATA EXTRACTOR")

# ---------- Helper Functions ----------

def extract_text_from_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text("text")
    return text.strip()

def extract_with_ai(batch_texts):
    # FIX: Use the latest active model name to avoid 404 errors
    MODEL_NAME = "gemini-2.5-flash" 
    
    prompt = f"""
    Act as an OCR data extraction expert. Extract the following from these Indian Shipping Bills:
    - SB No (Shipping Bill Number)
    - SB date (Format: DD-MMM-YY)
    - Port code (e.g., INHYD4)
    - LUT (Return 'Y' if 'LUT' is present in the status table, otherwise 'N')
    - IGST AMT (The Integrated Tax amount, numerical only)

    Return the results ONLY as a valid JSON ARRAY of objects. 
    Documents to process: {json.dumps(batch_texts)}
    """

    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt)
        
        # Strip potential markdown backticks from AI output
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        match = re.search(r"\[.*\]", clean_text, re.DOTALL)
        
        return json.loads(match.group(0)) if match else []
    except Exception as e:
        st.error(f"Extraction Error: {e}")
        return []

# ---------- UI Layout ----------

uploaded_files = st.file_uploader("Upload Shipping Bill PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    if st.button("Generate Excel Report"):
        all_data = []
        with st.spinner("Processing..."):
            for uploaded in uploaded_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded.read())
                    text = extract_text_from_pdf(tmp.name)
                os.remove(tmp.name)
                
                # Send text (first 10k chars to save tokens) to AI
                res = extract_with_ai([{"Source": uploaded.name, "Text": text[:10000]}])
                if res:
                    all_data.extend(res)

        if all_data:
            df = pd.DataFrame(all_data)
            
            # Match the exact column names you requested
            mapping = {
                "SB No": "SB No", 
                "SB date": "SB date", 
                "LUT": 'LUT "Y" or "N"', 
                "IGST AMT": '"IGST AMT"', 
                "Port code": '"Port code"'
            }
            df.rename(columns=mapping, inplace=True)
            
            st.success("✅ Extraction Successful!")
            st.dataframe(df)

            # Excel Export logic using openpyxl
            excel_name = "Shipping_Bill_Report.xlsx"
            df.to_excel(excel_name, index=False)
            with open(excel_name, "rb") as f:
                st.download_button(
                    label="📥 Download Excel File",
                    data=f,
                    file_name=excel_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
