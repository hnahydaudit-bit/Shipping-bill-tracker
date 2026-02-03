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

st.set_page_config(page_title="Shipping Bill Prototype", layout="wide")
st.title("🚢 SHIPPING BILL DATA EXTRACTOR")

# ---------- Helper Functions ----------

def extract_text_from_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text("text")
    return text.strip()

def extract_with_ai(batch_texts):
    # Prototyping Tip: 'gemini-1.5-flash' is currently the most 
    # compatible stable model name across all account types.
    MODEL_NAME = "gemini-1.5-flash"
    
    prompt = f"""
    You are a data extraction tool. Extract these fields from Indian Customs Shipping Bills:
    - SB No
    - SB date
    - Port code
    - LUT (Return 'Y' if exported under LUT, 'N' if IGST paid)
    - IGST AMT (Numeric only)

    Return ONLY a JSON ARRAY of objects. 
    Documents: {json.dumps(batch_texts)}
    """

    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt)
        
        # Clean AI response for JSON parsing
        text_content = response.text.replace('```json', '').replace('```', '').strip()
        match = re.search(r"\[.*\]", text_content, re.DOTALL)
        
        return json.loads(match.group(0)) if match else []
    except Exception as e:
        # Handle the common "Limit 0" Quota error gracefully
        if "429" in str(e):
            st.error("🚨 **Quota Error (429):** Your API key has a limit of 0. "
                     "To fix this for your prototype, you must link a billing account "
                     "in Google AI Studio (Settings > Plan).")
        else:
            st.error(f"Extraction Error: {e}")
        return []

# ---------- UI Layout ----------

st.sidebar.header("Prototype Debugger")
if st.sidebar.button("Test API Connection"):
    try:
        # Check which models your specific key is allowed to use
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        st.sidebar.success("Connection Successful!")
        st.sidebar.write("Your allowed models:", models)
    except Exception as e:
        st.sidebar.error(f"API Key Error: {e}")

uploaded_files = st.file_uploader("Upload Shipping Bill PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    if st.button("Extract Data"):
        all_data = []
        with st.spinner("AI is reading documents..."):
            for uploaded in uploaded_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded.read())
                    text = extract_text_from_pdf(tmp.name)
                os.remove(tmp.name)
                
                # Limit text to 10k chars to keep it within free token windows
                res = extract_with_ai([{"Source": uploaded.name, "Text": text[:10000]}])
                if res:
                    all_data.extend(res)

        if all_data:
            df = pd.DataFrame(all_data)
            
            # Map columns to user-requested names
            mapping = {
                "SB No": "SB No", "SB date": "SB date", 
                "LUT": 'LUT "Y" or "N"', "IGST AMT": '"IGST AMT"', "Port code": '"Port code"'
            }
            df.rename(columns=mapping, inplace=True)
            
            st.success("Extraction Complete")
            st.dataframe(df)

            # Export to Excel
            excel_name = "Extracted_Shipping_Data.xlsx"
            df.to_excel(excel_name, index=False)
            with open(excel_name, "rb") as f:
                st.download_button("📥 Download Excel Report", f, file_name=excel_name)
