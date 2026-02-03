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
            # Adding page markers helps the AI locate the Page 1 Status table
            text += f"\n--- PAGE {page.number + 1} ---\n"
            text += page.get_text("text")
    return text.strip()

def extract_with_ai(file_text, file_name):
    # USE CASE: gemini-2.0-flash is the most stable for 2026 projects
    MODEL_NAME = "gemini-2.0-flash" 
    
    prompt = f"""
    You are a professional Customs Auditor. Extract data from this Indian Shipping Bill with 100% accuracy.
    
    CRITICAL INSTRUCTIONS:
    1. .INV NO.: Extract the Invoice Number (e.g., JEHIN/2025/00090).
    2. LUT STATUS: Go to Page 1. Locate the 'STATUS' table. Look specifically at column '11.LUT'.
       - If the value directly below '11.LUT' is 'N', return 'N'.
       - If the value directly below '11.LUT' is 'Y', return 'Y'.
       - DO NOT use the IGST amount or tax presence to guess this. Only use the table value.
    
    Required Fields (JSON ARRAY ONLY):
    - ".INV NO."
    - "SB No"
    - "SB date"
    - "Port code"
    - "LUT"
    - "IGST AMT"

    Document Name: {file_name}
    Content: {file_text}
    """

    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt)
        
        # Robust cleaning of AI response
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        match = re.search(r"\[.*\]", clean_text, re.DOTALL)
        
        return json.loads(match.group(0)) if match else []
    except Exception as e:
        # Handle Quota Limit 0 Error specifically for the user
        if "429" in str(e):
            st.error(f"Quota Error for {file_name}: Your API key has a 'Limit 0'. Please link a billing account in Google AI Studio to unlock the free tier.")
        elif "404" in str(e):
            st.error(f"Model Error: {MODEL_NAME} is not found. Check if your API key is restricted to specific regions.")
        else:
            st.error(f"Error: {e}")
        return []

# ---------- UI Layout ----------

uploaded_files = st.file_uploader("Upload Shipping Bill PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    if st.button("Generate Accurate Excel Report"):
        all_data = []
        with st.spinner("AI is scanning tables for accuracy..."):
            for uploaded in uploaded_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded.read())
                    text = extract_text_from_pdf(tmp.name)
                os.remove(tmp.name)
                
                # Send context to AI
                res = extract_with_ai(text, uploaded.name)
                if res:
                    all_data.extend(res)

        if all_data:
            df = pd.DataFrame(all_data)
            
            # 1. Ensure .INV NO. is the first column
            # 2. Reorder according to user preference
            desired_order = [".INV NO.", "SB No", "SB date", "Port code", "LUT", "IGST AMT"]
            
            # Safety check for missing columns
            for col in desired_order:
                if col not in df.columns:
                    df[col] = "Not Found"
            
            df = df[desired_order]

            # 3. Rename columns for final display
            df.rename(columns={
                "LUT": 'LUT "Y" or "N"', 
                "IGST AMT": '"IGST AMT"', 
                "Port code": '"Port code"'
            }, inplace=True)
            
            st.success("✅ Extraction Complete")
            st.dataframe(df)

            # 4. Excel Export
            excel_name = "Shipping_Bill_Data_Report.xlsx"
            df.to_excel(excel_name, index=False)
            with open(excel_name, "rb") as f:
                st.download_button("📥 Download Excel Report", f, file_name=excel_name)
