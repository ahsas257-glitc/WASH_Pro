# pages/about.py
from __future__ import annotations

import streamlit as st

from design.components.base_tool_ui import (
    apply_global_background,
    topbar,
    card_open,
    card_close,
)

# ============================================================
# Page Settings (MUST BE FIRST Streamlit call)
# ============================================================
st.set_page_config(
    page_title="About | WASH TPM",
    layout="wide",
    initial_sidebar_state="auto",
)

# ============================================================
# Background (Liquid Glass)
# ============================================================
apply_global_background(
    logo_path="assets/images/Logo_of_PPC.png",
    logo_opacity_light=0.08,
    logo_opacity_dark=0.15,
    intensity=1.0,
)

# ============================================================
# Topbar
# ============================================================
with st.container():
    topbar(
        title="WASH TPM Reporting System",
        subtitle="UNICEF WASH Programme | Third Party Monitoring (TPM)",
        right_chip="",
    )

# ============================================================
# Sections
# ============================================================
with st.container():
    card_open("1. Project Background")
    st.markdown(
        """
The **WASH (Water, Sanitation and Hygiene) Programme** aims to improve access to safe drinking water,
sanitation services, and hygiene practices in vulnerable communities.

As part of quality assurance and accountability mechanisms, **Third Party Monitoring (TPM)** is conducted
to independently assess the implementation, quality, and compliance of WASH interventions.

The WASH TPM Reporting System supports UNICEF and its partners by providing a structured, evidence-based
approach to documenting field monitoring results and generating standardized monitoring reports.
"""
    )
    card_close()

with st.container():
    card_open("2. Purpose of This Application")
    st.markdown(
        """
This Streamlit-based application has been developed to support **TPM field monitoring and reporting**
for UNICEF WASH projects.

The application enables monitors and engineers to:

- Review project information collected during field visits  
- Validate technical progress and compliance  
- Attach and review supporting evidence (photos and audio)  
- Record observations, findings, and recommendations  
- Generate standardized and printable monitoring reports (DOCX format)
"""
    )
    card_close()

with st.container():
    card_open("3. What the Application Does")
    st.markdown(
        """
The WASH TPM Reporting application performs the following core functions:

1. Allows users to select a monitoring **Tool** and **TPM ID**  
2. Loads project and monitoring data from Google Sheets  
3. Displays project details such as location, intervention type, visit date, and implementing partner  
4. Retrieves and previews photo and audio evidence from SurveyCTO attachments  
5. Enables selection of photos for:
   - Cover Page
   - Findings
   - Observations  
6. Supports component-wise documentation of:
   - Observations
   - Major findings (tabular format)
   - Recommendations  
7. Compiles all validated information into a structured **DOCX monitoring report**
"""
    )
    card_close()

with st.container():
    card_open("4. Data Sources")
    st.markdown(
        """
- **Google Sheets** – Primary source of structured TPM data  
- **SurveyCTO Attachments** – Source for evidence (photos, audio)  
- **User Inputs** – Narrative and validation info added by TPM user
"""
    )
    card_close()

with st.container():
    card_open("5. How to Use the Application")
    st.markdown(
        """
**Step 1:** Open the **Home** page  
**Step 2:** Select the relevant Tool (e.g., Tool 6)  
**Step 3:** Select the corresponding TPM ID  
**Step 4:** Click **Continue / Launch Tool**

**Inside the Tool page:**
- Review and edit general project information  
- Preview and select photo/audio evidence  
- Assign photos to report sections  
- Fill in observations, findings, and recommendations  

**Final Step:**  
Click **Generate DOCX Report** to export the final file.
"""
    )
    card_close()

with st.container():
    card_open("6. Notes & Troubleshooting")
    st.markdown(
        """
- If photos/audio don’t load: check your SurveyCTO credentials  
- If TPM ID isn’t found: verify Google Sheet config  
- One valid **cover photo** is required to generate the DOCX report  

**Security Tip:**  
Store SurveyCTO credentials in `secrets.toml` instead of manual entry.
"""
    )
    card_close()

st.caption("© UNICEF WASH TPM — Reporting System")
