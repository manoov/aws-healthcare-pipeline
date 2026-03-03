#!/usr/bin/env python3
"""
Healthcare Waveform Dashboard — Streamlit application for browsing,
visualizing, and querying AWS-stored medical waveform data.

Run:
    streamlit run dashboard/app.py
"""

import io
import json
import sys
import os

# Add project root so we can import aws_config / aws_query from the repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from aws_config import AWSConfig
from aws_query import AthenaQuerier, DynamoDBQuerier

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Healthcare Waveform Dashboard",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Dark-mode inspired premium styling */
    .main .block-container { padding-top: 2rem; }

    .metric-card {
        background: linear-gradient(135deg, #1e3a5f 0%, #0d1b2a 100%);
        border-radius: 12px;
        padding: 1.2rem;
        color: #e0e0e0;
        text-align: center;
        border: 1px solid #2a4a6b;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    .metric-card h3 {
        color: #64b5f6;
        font-size: 0.85rem;
        margin-bottom: 0.3rem;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .metric-card .value {
        font-size: 2rem;
        font-weight: 700;
        color: #ffffff;
    }

    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .status-uploaded { background: #1565c0; color: #fff; }
    .status-processing { background: #f57f17; color: #fff; }
    .status-completed { background: #2e7d32; color: #fff; }
    .status-lambda_processed { background: #6a1b9a; color: #fff; }

    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #0d1b2a;
        border-radius: 8px;
        padding: 0.5rem 1.5rem;
        color: #64b5f6;
        border: 1px solid #2a4a6b;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1e3a5f;
        color: #ffffff;
        border-color: #42a5f5;
    }

    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1b2a 0%, #1b2838 100%);
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar — Configuration
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🏥 Pipeline Config")
    stack_name = st.text_input("CloudFormation Stack", value="healthcare-waveform-pipeline")
    region = st.selectbox("AWS Region", [
        "us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1", "ca-central-1"
    ])

    st.markdown("---")
    st.markdown("### 🔗 Quick Links")
    st.markdown(f"[S3 Console](https://s3.console.aws.amazon.com/s3/home?region={region})")
    st.markdown(f"[DynamoDB Console](https://{region}.console.aws.amazon.com/dynamodbv2/home?region={region})")
    st.markdown(f"[Athena Console](https://{region}.console.aws.amazon.com/athena/home?region={region})")


# ---------------------------------------------------------------------------
# Initialize AWS clients
# ---------------------------------------------------------------------------
@st.cache_resource
def get_config(stack, reg):
    return AWSConfig(stack_name=stack, region=reg)


@st.cache_resource
def get_dynamodb_querier(_cfg):
    return DynamoDBQuerier(_cfg)


@st.cache_resource
def get_athena_querier(_cfg):
    return AthenaQuerier(_cfg)


cfg = get_config(stack_name, region)

# We wrap in try/except so the dashboard still loads without AWS creds
aws_available = True
try:
    ddb = get_dynamodb_querier(cfg)
    athena = get_athena_querier(cfg)
except Exception as e:
    aws_available = False
    st.warning(f"⚠️ AWS connection failed: {e}. Dashboard running in demo mode.")


# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------
st.markdown("""
# 🏥 Healthcare Waveform Pipeline Dashboard
**Real-time monitoring and analysis of MIMIC medical waveform data on AWS**
""")


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "📋 Records Browser",
    "📈 Waveform Viewer",
    "📊 Metrics Dashboard",
    "🔍 Query Console",
])


# ===== TAB 1: Records Browser =============================================
with tab1:
    st.header("📋 Records Browser")

    if not aws_available:
        st.info("Connect to AWS to browse records stored in DynamoDB.")
        # Demo mode with sample data
        demo_data = pd.DataFrame({
            "record_id": ["rec_001_abc12345", "rec_002_def67890", "rec_003_ghi11111"],
            "patient_id": ["p10000032", "p10000032", "p10000098"],
            "channels": [["II", "V1"], ["ABP", "ART"], ["II"]],
            "processing_status": ["completed", "uploaded", "processing"],
            "sampling_freq": ["500.0", "125.0", "500.0"],
            "duration_sec": ["10.0", "30.0", "15.5"],
        })
        st.dataframe(demo_data, use_container_width=True)
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            filter_patient = st.text_input("Filter by Patient ID", placeholder="e.g. p10000032")
        with col2:
            filter_status = st.selectbox("Filter by Status", [
                "All", "uploaded", "processing", "completed", "lambda_processed"
            ])
        with col3:
            max_records = st.slider("Max records", 10, 500, 100)

        if st.button("🔄 Refresh Records", type="primary"):
            st.cache_data.clear()

        try:
            if filter_patient:
                records = ddb.get_patient_records(filter_patient)
            elif filter_status != "All":
                records = ddb.get_records_by_status(filter_status)
            else:
                records = ddb.scan_all_records(limit=max_records)

            if records:
                df = pd.DataFrame(records)
                # Summary metrics
                col_a, col_b, col_c, col_d = st.columns(4)
                with col_a:
                    st.markdown(f"""<div class="metric-card">
                        <h3>Total Records</h3>
                        <div class="value">{len(df)}</div>
                    </div>""", unsafe_allow_html=True)
                with col_b:
                    completed = len(df[df.get("processing_status", "") == "completed"]) if "processing_status" in df else 0
                    st.markdown(f"""<div class="metric-card">
                        <h3>Completed</h3>
                        <div class="value">{completed}</div>
                    </div>""", unsafe_allow_html=True)
                with col_c:
                    patients = df["patient_id"].nunique() if "patient_id" in df else 0
                    st.markdown(f"""<div class="metric-card">
                        <h3>Patients</h3>
                        <div class="value">{patients}</div>
                    </div>""", unsafe_allow_html=True)
                with col_d:
                    pending = len(df[df.get("processing_status", "") == "uploaded"]) if "processing_status" in df else 0
                    st.markdown(f"""<div class="metric-card">
                        <h3>Pending</h3>
                        <div class="value">{pending}</div>
                    </div>""", unsafe_allow_html=True)

                st.markdown("---")
                st.dataframe(df, use_container_width=True, height=400)
            else:
                st.info("No records found. Upload some waveforms first!")
        except Exception as e:
            st.error(f"Error fetching records: {e}")


# ===== TAB 2: Waveform Viewer =============================================
with tab2:
    st.header("📈 Waveform Viewer")

    if not aws_available:
        st.info("Connect to AWS to view waveforms from S3.")
        # Demo waveform
        t = np.linspace(0, 2 * np.pi * 5, 2000)
        demo_signal = np.sin(t) + 0.3 * np.sin(3 * t) + 0.1 * np.random.randn(len(t))
        demo_recon = np.sin(t) + 0.3 * np.sin(3 * t)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            y=demo_signal[:500], mode="lines", name="Original",
            line=dict(color="#42a5f5", width=1.5),
        ))
        fig.add_trace(go.Scatter(
            y=demo_recon[:500], mode="lines", name="Reconstructed",
            line=dict(color="#ef5350", width=1.5, dash="dash"),
        ))
        fig.update_layout(
            title="Demo: ECG-like Waveform (Original vs Reconstructed)",
            template="plotly_dark",
            height=450,
            xaxis_title="Sample Index",
            yaxis_title="Amplitude",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        record_id = st.text_input("Enter Record ID to view")
        plot_length = st.slider("Plot length (samples)", 200, 10000, 2000)

        if record_id and st.button("📈 Load Waveform", type="primary"):
            try:
                s3 = cfg.s3_client()
                result_key = f"{cfg.processed_prefix}{record_id}/waveform_results.csv"

                obj = s3.get_object(Bucket=cfg.processed_bucket, Key=result_key)
                df = pd.read_csv(io.BytesIO(obj["Body"].read()))

                df_plot = df.head(plot_length)

                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df_plot["sample_index"],
                    y=df_plot["original_value"],
                    mode="lines",
                    name="Original",
                    line=dict(color="#42a5f5", width=1.5),
                ))
                fig.add_trace(go.Scatter(
                    x=df_plot["sample_index"],
                    y=df_plot["reconstructed_value"],
                    mode="lines",
                    name="Reconstructed",
                    line=dict(color="#ef5350", width=1.5, dash="dash"),
                ))
                fig.update_layout(
                    title=f"Waveform: {record_id} ({df_plot['channel'].iloc[0]})",
                    template="plotly_dark",
                    height=500,
                    xaxis_title="Sample Index",
                    yaxis_title="Amplitude",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                )
                st.plotly_chart(fig, use_container_width=True)

                # Error distribution
                if "original_value" in df.columns and "reconstructed_value" in df.columns:
                    errors = df["original_value"] - df["reconstructed_value"]
                    fig_err = go.Figure()
                    fig_err.add_trace(go.Histogram(
                        x=errors, nbinsx=100,
                        marker_color="#7e57c2",
                        opacity=0.8,
                    ))
                    fig_err.update_layout(
                        title="Reconstruction Error Distribution",
                        template="plotly_dark",
                        height=350,
                        xaxis_title="Error (Original - Reconstructed)",
                        yaxis_title="Count",
                    )
                    st.plotly_chart(fig_err, use_container_width=True)

            except Exception as e:
                st.error(f"Error loading waveform: {e}")


# ===== TAB 3: Metrics Dashboard ===========================================
with tab3:
    st.header("📊 Compression Metrics")

    if not aws_available:
        st.info("Connect to AWS to view processing metrics.")
        # Demo metrics
        demo_metrics = pd.DataFrame({
            "Record": ["rec_001", "rec_002", "rec_003", "rec_004"],
            "Quality": [0.962, 0.975, 0.948, 0.981],
            "MSE": [0.00021, 0.00012, 0.00038, 0.00009],
            "MAE": [0.00856, 0.00612, 0.01234, 0.00456],
            "PRD%": [1.024, 0.812, 1.456, 0.623],
        })

        col1, col2 = st.columns(2)
        with col1:
            fig_q = go.Figure()
            fig_q.add_trace(go.Bar(
                x=demo_metrics["Record"],
                y=demo_metrics["Quality"],
                marker_color=["#2e7d32" if q > 0.95 else "#f57f17" for q in demo_metrics["Quality"]],
                text=[f"{q:.3f}" for q in demo_metrics["Quality"]],
                textposition="outside",
            ))
            fig_q.update_layout(
                title="Reconstruction Quality Score",
                template="plotly_dark",
                height=400,
                yaxis_range=[0.9, 1.0],
                yaxis_title="Quality (1.0 = perfect)",
            )
            st.plotly_chart(fig_q, use_container_width=True)

        with col2:
            fig_m = go.Figure()
            fig_m.add_trace(go.Bar(
                name="MSE", x=demo_metrics["Record"], y=demo_metrics["MSE"],
                marker_color="#42a5f5",
            ))
            fig_m.add_trace(go.Bar(
                name="MAE", x=demo_metrics["Record"], y=demo_metrics["MAE"],
                marker_color="#ef5350",
            ))
            fig_m.update_layout(
                title="Error Metrics per Record",
                template="plotly_dark",
                height=400,
                barmode="group",
                yaxis_title="Error Value",
            )
            st.plotly_chart(fig_m, use_container_width=True)

        st.dataframe(demo_metrics, use_container_width=True)
    else:
        if st.button("🔄 Load Metrics", type="primary"):
            try:
                records = ddb.scan_all_records(limit=500)
                completed = [
                    r for r in records if r.get("processing_status") == "completed"
                ]

                if completed:
                    metrics_data = []
                    for r in completed:
                        metrics_data.append({
                            "Record": r["record_id"][:20],
                            "Quality": float(r.get("metric_quality", 0)),
                            "MSE": float(r.get("metric_mse", 0)),
                            "MAE": float(r.get("metric_mae", 0)),
                            "PRD%": float(r.get("metric_prd", 0)),
                            "RMS": float(r.get("metric_rms", 0)),
                        })
                    df_m = pd.DataFrame(metrics_data)

                    col1, col2 = st.columns(2)
                    with col1:
                        fig_q = go.Figure()
                        fig_q.add_trace(go.Bar(
                            x=df_m["Record"], y=df_m["Quality"],
                            marker_color=["#2e7d32" if q > 0.95 else "#f57f17" for q in df_m["Quality"]],
                        ))
                        fig_q.update_layout(
                            title="Reconstruction Quality",
                            template="plotly_dark", height=400,
                        )
                        st.plotly_chart(fig_q, use_container_width=True)

                    with col2:
                        fig_m = go.Figure()
                        fig_m.add_trace(go.Bar(name="MSE", x=df_m["Record"], y=df_m["MSE"]))
                        fig_m.add_trace(go.Bar(name="MAE", x=df_m["Record"], y=df_m["MAE"]))
                        fig_m.update_layout(
                            title="Error Metrics",
                            template="plotly_dark", height=400, barmode="group",
                        )
                        st.plotly_chart(fig_m, use_container_width=True)

                    st.dataframe(df_m, use_container_width=True)
                else:
                    st.info("No completed records yet. Process some waveforms first!")
            except Exception as e:
                st.error(f"Error loading metrics: {e}")


# ===== TAB 4: Query Console ===============================================
with tab4:
    st.header("🔍 Query Console")

    query_type = st.radio("Query Type", ["Athena (SQL)", "DynamoDB (Key Lookup)"], horizontal=True)

    if query_type == "Athena (SQL)":
        st.markdown("Run SQL queries against processed waveform data in S3.")
        default_sql = """SELECT record_id, channel,
       COUNT(*) as sample_count,
       AVG(CAST(original_value AS DOUBLE)) as avg_original,
       AVG(CAST(reconstructed_value AS DOUBLE)) as avg_reconstructed
FROM processed_waveforms
GROUP BY record_id, channel
LIMIT 20"""

        sql = st.text_area("SQL Query", value=default_sql, height=180)

        if st.button("▶ Execute Query", type="primary"):
            if not aws_available:
                st.warning("AWS not connected. Cannot run Athena queries.")
            else:
                with st.spinner("Running Athena query..."):
                    try:
                        df = athena.run_query(sql)
                        st.success(f"✅ Query returned {len(df)} rows")
                        st.dataframe(df, use_container_width=True)

                        # Download button
                        csv_data = df.to_csv(index=False)
                        st.download_button(
                            "📥 Download as CSV",
                            csv_data,
                            "query_results.csv",
                            "text/csv",
                        )
                    except Exception as e:
                        st.error(f"Query failed: {e}")

    else:
        st.markdown("Look up records from the DynamoDB metadata table.")
        col1, col2 = st.columns(2)
        with col1:
            lookup_record = st.text_input("Record ID")
        with col2:
            lookup_patient = st.text_input("Patient ID")

        if st.button("🔍 Search", type="primary"):
            if not aws_available:
                st.warning("AWS not connected.")
            else:
                try:
                    if lookup_record:
                        item = ddb.get_record(lookup_record)
                        if item:
                            st.json(json.loads(json.dumps(item, default=str)))
                        else:
                            st.warning("Record not found.")
                    elif lookup_patient:
                        items = ddb.get_patient_records(lookup_patient)
                        if items:
                            st.dataframe(pd.DataFrame(items), use_container_width=True)
                        else:
                            st.warning("No records for this patient.")
                    else:
                        st.info("Enter a Record ID or Patient ID to search.")
                except Exception as e:
                    st.error(f"Lookup failed: {e}")


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    """<div style="text-align: center; color: #666; font-size: 0.85rem;">
    Healthcare Waveform Pipeline Dashboard • Built with Streamlit + AWS •
    Data source: MIMIC-IV Waveforms
    </div>""",
    unsafe_allow_html=True,
)
