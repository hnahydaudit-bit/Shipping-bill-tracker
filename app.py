import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import google.generativeai as genai
import tempfile
import os
import json
import re

# 🔑 Configure Gemini
# Ensure you have "GEMINI_API_KEY" set in your Streamlit Secrets or Environment Variables
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Missing Gemini API Key. Please add it to Streamlit Secrets.")

# 🎨 Page setup
st.set_page_config(page_title="SHIPPING BILL EXTRACTOR", page_icon="🚢")
st.title("🚢 SHIPPING BILL DATA EXTRACTOR")

# ---------- Helper Functions ----------

def extract_text_from_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text("text")
    return text.strip()

def extract_shipping_details_with_ai(batch_texts):
    prompt = f"""
You are an expert in Indian Customs Shipping Bills (ICEGATE).
For EACH document provided, extract the specific details and return a JSON ARRAY.

Fields required for each object:
- SB No (Shipping Bill Number)
- SB Date (Date of Shipping Bill)
- Port Code (6-character code, e.g., INHYD4)
- LUT (Return "Y" if exported under LUT/Bond, "N" if IGST was paid)
- IGST AMT (The total IGST amount mentioned in the tax/summary section)
- Source (The filename)

VERY IMPORTANT INSTRUCTIONS:
1. "LUT" Logic: Look at the 'LUT' or 'STATUS' boxes. If the export is Zero Rated under LUT, mark "Y". If IGST amount is present and paid, mark "N".
2. "IGST AMT": Extract the numerical value only. If not found, return 0.
3. If a field is missing, return "Not Found".
4. Return ONLY valid JSON. No markdown, no extra text.

Documents:
{json.dumps(batch_texts, indent=2)}
"""

    model = genai.GenerativeModel("gemini-1.5-flash") # Using 1.5-flash for speed and cost-efficiency
    response = model.generate_content(prompt)

    try:
        # Clean response string to ensure it's valid JSON
        raw_text = response.text
        match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return []
    except Exception as e:
        st.error(f"Error parsing AI response: {e}")
        return []

# ---------- Streamlit UI ----------

uploaded_files = st.file_uploader(
    "📤 Upload Shipping Bill PDFs",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    if st.button("Process Shipping Bills"):
        st.info("⏳ Analyzing documents... please wait.")
        batch_texts = []

        for uploaded in uploaded_files:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded.read())
                tmp_path = tmp.name

            text = extract_text_from_pdf(tmp_path)
            os.remove(tmp_path)

            batch_texts.append({
                "Source": uploaded.name,
                "Text": text[:10000] # Sending first 10k chars to stay within limits while getting key data
            })

        results = extract_shipping_details_with_ai(batch_texts)

        if results:
            columns = ["SB No", "SB Date", "Port Code", "LUT", "IGST AMT", "Source"]
            df = pd.DataFrame(results, columns=columns)

            # Ensure Column names match user request exactly
            df.rename(columns={"LUT": 'LUT "Y" or "N"', "IGST AMT": '"IGST AMT"', "Port Code": '"Port code"'}, inplace=True)

            st.success("✅ Extraction completed")
            st.dataframe(df, use_container_width=True)

            # Excel Download
            out_file = "Shipping_Bill_Data.xlsx"
            df.to_excel(out_file, index=False)

            with open(out_file, "rb") as f:
                st.download_button(
                    "📥 Download Excel",
                    f,
                    file_name="Shipping_Bill_Data.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.warning("No data could be extracted. Please check the PDF format.")
