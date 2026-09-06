import streamlit as st
import requests
import json
import os

API_URL = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="DocAgent", page_icon="🧾", layout="wide")
st.title("🧾 DocAgent — Invoice Processing Agent")
st.markdown("Upload an invoice document (PDF) to automatically extract data, validate against compliance rules, detect anomalies, and route for approval.")

uploaded_file = st.file_uploader("Upload Invoice (PDF)", type=["pdf", "txt"])

if uploaded_file is not None and st.button("🚀 Process Invoice", type="primary"):
    with st.spinner("Agent is processing the document..."):
        try:
            # Send file to FastAPI backend
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            response = requests.post(f"{API_URL}/process", files=files, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                
                # Decision Banner
                decision = result.get("decision", "unknown")
                risk_score = result.get("risk_score", 0.0)
                level = result.get("approval_level", "unknown").upper()
                
                if decision == "auto_approve":
                    st.success(f"✅ AUTO-APPROVED | Risk: {risk_score:.0%} | Level: {level}")
                elif decision == "flag_review":
                    st.warning(f"⚠️ FLAGGED FOR REVIEW | Risk: {risk_score:.0%} | Level: {level}")
                elif decision == "reject":
                    st.error(f"❌ REJECTED | Risk: {risk_score:.0%} | Level: {level}")
                else:
                    st.info(f"ℹ️ DECISION PENDING | Risk: {risk_score:.0%}")
                    
                st.markdown(f"**Reasoning:** {result.get('reasoning', 'N/A')}")
                st.divider()

                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader("📄 Extracted Data")
                    invoice_data = result.get("invoice")
                    if invoice_data:
                        st.json(invoice_data)
                    else:
                        st.info("No data extracted.")
                        
                with col2:
                    st.subheader("🛡️ Compliance & Anomalies")
                    
                    # Validation Results
                    st.markdown("**Validation Checks:**")
                    validations = result.get("validation_results", [])
                    if not validations:
                        st.write("No compliance checks run.")
                    for v in validations:
                        icon = "✅" if v.get("passed") else "❌"
                        st.write(f"{icon} **{v.get('rule_name', 'Rule')}**: {v.get('message', '')}")
                        
                    st.markdown("---")
                    
                    # Anomalies
                    st.markdown("**Anomalies & Fraud Detection:**")
                    anomalies = result.get("anomalies", [])
                    if anomalies:
                        for a in anomalies:
                            st.warning(f"{a.get('type')}: {a.get('message')}")
                    else:
                        st.success("No anomalies detected.")
                
                st.divider()
                st.subheader("📋 Agent Audit Trail")
                with st.expander("View Full Step-by-Step Audit Log", expanded=False):
                    for entry in result.get("audit_trail", []):
                        st.text(f"[{entry.get('timestamp')[:19]}] {entry.get('step').upper()} — {entry.get('detail')}")

            else:
                st.error(f"Error from server: {response.status_code}")
                try:
                    st.json(response.json())
                except:
                    st.write(response.text)
                    
        except requests.exceptions.ConnectionError:
            st.error(f"Could not connect to the backend API at {API_URL}. Is the FastAPI server running?")
        except Exception as e:
            st.error(f"An error occurred: {e}")
