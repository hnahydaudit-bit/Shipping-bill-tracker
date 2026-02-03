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
            # Use 'dict' mode to preserve structural proximity for higher accuracy
            text += page.get_text("text")
    return text.strip()

def extract_with_ai(batch_texts):
    # Use the most stable high-performance model
    MODEL_NAME = "gemini-1.5-flash" 
    
    prompt = f"""
    You are a professional customs auditor. Extract data from these Indian Shipping Bills with 100% accuracy.
    
    CRITICAL INSTRUCTION FOR LUT: 
    Look at the 'STATUS' table (usually Page 1). Find column '11.LUT'. 
    If the value directly below '11.LUT' is 'N', return 'N'. 
    If it is 'Y', return 'Y'. 
    DO NOT guess based on IGST amounts. Look ONLY at the status indicator.

    Fields to Extract:
    1. .INV NO. (Invoice Number - usually found in PART-III or near the top)
    2. SB No (Shipping Bill Number)
    3. SB date (Format: DD-MMM-YY)
    4. Port code (e.g., INHYD4)
    5. LUT (Strictly 'Y' or 'N' from field 11)
    6. IGST AMT (Numeric value from the Integrated Tax field)

    Return results ONLY as a JSON ARRAY.
    Documents: {json.dumps(batch_texts)}
    """

    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt)
        
        # Clean response
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        match = re.search(r"\[.*\]", clean_text, re.DOTALL)
        
        return json.loads(match.group(0)) if match else []
    except Exception as e:
        st.error(f"Extraction Error: {e}")
        return []

# ---------- UI Layout ----------

uploaded_files = st.file_uploader("Upload Shipping Bill PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    if st.button("Generate Accurate Excel Report"):
        all_data = []
        with st.spinner("AI is performing deep scan for accuracy..."):
            for uploaded in uploaded_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded.read())
                    text = extract_text_from_pdf(tmp.name)
                os.remove(tmp.name)
                
                # Send text (first 15k chars for deep context)
                res = extract_with_ai([{"Source": uploaded.name, "Text": text[:15000]}])
                if res:
                    all_data.extend(res)

        if all_data:
            df = pd.DataFrame(all_data)
            
            # Reorder columns to ensure .INV NO. is first
            desired_order = [".INV NO.", "SB No", "SB date", "Port code", "LUT", "IGST AMT"]
            
            # Ensure all columns exist to prevent errors
            for col in desired_order:
                if col not in df.columns:
                    df[col] = "Not Found"
            
            df = df[desired_order]

            # Rename columns to your exact required labels
            final_mapping = {
                ".INV NO.": ".INV NO.",
                "SB No": "SB No", 
                "SB date": "SB date", 
                "LUT": 'LUT "Y" or "N"', 
                "IGST AMT": '"IGST AMT"', 
                "Port code": '"Port code"'
            }
            df.rename(columns=final_mapping, inplace=True)
            
            st.success("✅ Extraction Complete")
            st.dataframe(df)

            # Excel Export
            excel_name = "Final_Shipping_Bill_Data.xlsx"
            df.to_excel(excel_name, index=False)
            with open(excel_name, "rb") as f:
                st.download_button("📥 Download Accurate Excel", f, file_name=excel_name)
