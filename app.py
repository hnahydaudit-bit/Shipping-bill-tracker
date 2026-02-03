import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import google.generativeai as genai
import tempfile
import os
import json
import re

# 🔑 Configure Gemini
# This looks for the key in your Streamlit Cloud Secrets
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Missing Gemini API Key. Please add it to Streamlit Secrets as GEMINI_API_KEY.")

# 🎨 Page setup
st.set_page_config(page_title="SHIPPING BILL EXTRACTOR", page_icon="🚢", layout="wide")
st.title("🚢 SHIPPING BILL DATA EXTRACTOR")

# ---------- Helper Functions ----------

def extract_text_from_pdf(file_path):
    text = ""
    try:
        with fitz.open(file_path) as doc:
            for page in doc:
                text += page.get_text("text")
        return text.strip()
    except Exception as e:
        return f"Error reading PDF: {e}"

def extract_shipping_details_with_ai(batch_texts):
    prompt = f"""
You are an expert in Indian Customs Shipping Bills (ICEGATE).
For EACH document provided, extract the specific details and return a JSON ARRAY.

Fields required for each object:
- SB No
- SB Date
- Port Code
- LUT (Return "Y" if exported under LUT/Bond status, "N" if IGST was paid)
- IGST AMT (The total Integrated Tax amount. If zero or not found, return 0)
- Source (The filename)

VERY IMPORTANT:
1. Return ONLY a valid JSON array. 
2. Do not include markdown formatting like ```json ... ```.
3. If data is missing, use "Not Found".

Documents:
{json.dumps(batch_texts, indent=2)}
"""

    # FIX: Using the correct, standard model identifier
    model = genai.GenerativeModel("gemini-1.5-flash") 
    
    try:
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        
        # Clean potential markdown backticks if AI includes them
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```json\s*|```$", "", raw_text, flags=re.MULTILINE)
        
        # Find the JSON array part
        match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        else:
            # Fallback if AI didn't provide brackets
            return json.loads(raw_text)
            
    except Exception as e:
        st.error(f"AI Extraction Error: {e}")
        return []

# ---------- Streamlit UI ----------

uploaded_files = st.file_uploader(
    "📤 Upload Shipping Bill PDFs (ICEGATE Format)",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    if st.button("Extract Data"):
        st.info("⏳ Processing files... This may take a moment.")
        batch_texts = []

        for uploaded in uploaded_files:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded.read())
                tmp_path = tmp.name

            text = extract_text_from_pdf(tmp_path)
            os.remove(tmp_path)

            # Extract first 15,000 characters to cover multi-page bills without hitting token limits
            batch_texts.append({
                "Source": uploaded.name,
                "Text": text[:15000] 
            })

        results = extract_shipping_details_with_ai(batch_texts)

        if results:
            # Define requested column names
            # User requirement: "SB No", "SB date", LUT "Y" or "N", "IGST AMT", "Port code"
            df = pd.DataFrame(results)
            
            # Mapping extracted keys to requested column names
            rename_map = {
                "SB No": "SB No",
                "SB Date": "SB date",
                "LUT": 'LUT "Y" or "N"',
                "IGST AMT": '"IGST AMT"',
                "Port Code": '"Port code"'
            }
            
            df.rename(columns=rename_map, inplace=True)
            
            # Keep only the requested columns (and Source for reference)
            final_cols = ["SB No", "SB date", 'LUT "Y" or "N"', '"IGST AMT"', '"Port code"', "Source"]
            df = df[[c for c in final_cols if c in df.columns]]

            st.success(f"✅ Extracted data from {len(results)} file(s)")
            st.dataframe(df, use_container_width=True)

            # Create Excel Download
            try:
                out_file = "Shipping_Bill_Report.xlsx"
                df.to_excel(out_file, index=False)

                with open(out_file, "rb") as f:
                    st.download_button(
                        label="📥 Download Excel Report",
                        data=f,
                        file_name="Shipping_Bill_Report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            except Exception as e:
                st.error(f"Error creating Excel: {e}")
        else:
            st.error("No data could be extracted. Please ensure the PDF is a valid Shipping Bill.")
