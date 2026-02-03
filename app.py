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
    # Setting the API key
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Missing GEMINI_API_KEY in Streamlit Secrets.")

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
    # FIX: Using the newest stable model name
    # Ensure you are using the latest version of google-generativeai
    MODEL_NAME = "gemini-2.0-flash-lite" 
    
    prompt = f"""
    Extract data from these Shipping Bills into a JSON ARRAY. 
    Required Fields: "SB No", "SB date", "LUT", "IGST AMT", "Port code", "Source".
    LUT: 'Y' if exported under LUT, 'N' if IGST paid.
    
    Return ONLY a JSON array. 
    Documents: {json.dumps(batch_texts)}
    """

    try:
        # Initializing the model
        model = genai.GenerativeModel(MODEL_NAME)
        
        # Calling the API
        response = model.generate_content(prompt)
        
        # Standard cleaning of the AI response
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        match = re.search(r"\[.*\]", clean_text, re.DOTALL)
        
        if match:
            return json.loads(match.group(0))
        return []
        
    except Exception as e:
        # Specifically handling 404 (Model Not Found) or 429 (Quota) errors
        if "404" in str(e):
            st.error(f"Model Error: {MODEL_NAME} not found. Your API key might not have access to this model yet. Try changing the model name to 'gemini-1.5-flash'.")
        elif "429" in str(e):
            st.error("Quota Exceeded: Please add a billing account to your Google AI Studio project to unlock your limits.")
        else:
            st.error(f"Error: {e}")
        return []

# ---------- Main UI ----------
uploaded_files = st.file_uploader("Upload Shipping Bill PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    if st.button("Process Documents"):
        all_results = []
        progress_bar = st.progress(0)
        
        for idx, uploaded in enumerate(uploaded_files):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded.read())
                text = extract_text_from_pdf(tmp.name)
            os.remove(tmp.name)
            
            # Send small batches to stay within free token limits
            res = extract_with_ai([{"Source": uploaded.name, "Text": text[:10000]}])
            if res:
                all_results.extend(res)
            
            progress_bar.progress((idx + 1) / len(uploaded_files))

        if all_results:
            df = pd.DataFrame(all_results)
            # Final column cleanup to match your specific requirement
            final_map = {
                "SB No": "SB No", 
                "SB date": "SB date", 
                "LUT": 'LUT "Y" or "N"', 
                "IGST AMT": '"IGST AMT"', 
                "Port code": '"Port code"'
            }
            df.rename(columns=final_map, inplace=True)
            
            st.success("Extraction Complete")
            st.dataframe(df)

            # Excel Export
            out_file = "Shipping_Bill_Data.xlsx"
            df.to_excel(out_file, index=False)
            with open(out_file, "rb") as f:
                st.download_button("📥 Download Excel", f, file_name="Shipping_Bill_Data.xlsx")
