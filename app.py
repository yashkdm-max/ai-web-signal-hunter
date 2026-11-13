import json
import pandas as pd
import streamlit as st

from src.config import LLM_PROVIDER
from src.crawler import ResponsibleCrawler
from src.analyzer import SignalAnalyzer
from src.ranker import rank_opportunities
from src.database import save_run_results

st.set_page_config(
    page_title="AI Web Signal Hunter",
    page_icon="🎯",
    layout="wide"
)

st.title("🎯 AI Web Signal Hunter")
st.caption("Turn unstructured public web pages into ranked, evidence-backed market opportunities.")

# Sidebar Controls
with st.sidebar:
    st.header("1. Research Configuration")
    topic = st.text_input(
        "Research Topic / Question",
        value="What problems do small businesses mention about WhatsApp automation tools?"
    )
    keywords = st.text_input(
        "Optional Keywords (comma-separated)",
        placeholder="pricing, ban, API, support"
    )
    max_pages = st.slider("Max Pages to Crawl", min_value=5, max_value=40, value=25, step=5)
    provider = st.selectbox(
        "LLM Provider",
        options=["gemini", "groq"],
        index=0 if LLM_PROVIDER == "gemini" else 1
    )

    run_btn = st.button("🚀 Hunt Signals", type="primary", use_container_width=True)

    st.divider()
    st.markdown("### 📐 Ranking Formula")
    st.code(
        "Base = 0.40*Rel + 0.35*Urg + 0.25*Conf\n"
        "Mult = 1 + 0.15*ln(Sources) + 0.10*(Domains-1)\n"
        "Score = min(100, Base * Mult)",
        language="text"
    )

# Session State Initialization
if "signals" not in st.session_state:
    st.session_state.signals = []
if "opportunities" not in st.session_state:
    st.session_state.opportunities = []
if "current_topic" not in st.session_state:
    st.session_state.current_topic = ""

# Execution Pipeline
if run_btn:
    if not topic.strip():
        st.error("Please enter a research topic.")
    else:
        status_box = st.status("Running AI Web Signal Hunter pipeline...", expanded=True)
        try:
            crawler = ResponsibleCrawler()
            pages = crawler.crawl_and_clean(
                topic=topic,
                keywords=keywords,
                max_pages=max_pages,
                progress_callback=lambda msg: status_box.write(f"🌐 {msg}")
            )

            if not pages:
                status_box.update(label="No crawlable pages found.", state="error")
                st.stop()

            unique_domains = len({p["domain"] for p in pages})
            status_box.write(f"✅ Crawled & deduplicated **{len(pages)} pages** across **{unique_domains} domains**.")

            analyzer = SignalAnalyzer(provider=provider)
            extracted_signals = []
            progress_bar = st.progress(0)

            for idx, page in enumerate(pages):
                status_box.write(f"🧠 Analyzing ({idx+1}/{len(pages)}): {page['title'][:55]}...")
                sig = analyzer.analyze_page(topic, page)
                extracted_signals.append(sig)
                progress_bar.progress((idx + 1) / len(pages))

            status_box.write("📊 Grouping themes & ranking top opportunities...")
            top_opps = rank_opportunities(topic, extracted_signals, analyzer, top_k=5)

            save_run_results(topic, extracted_signals, top_opps)

            st.session_state.signals = extracted_signals
            st.session_state.opportunities = top_opps
            st.session_state.current_topic = topic

            status_box.update(label="Hunt complete!", state="complete", expanded=False)

        except Exception as e:
            status_box.update(label="Pipeline error", state="error")
            st.error(f"Error: {e}")

# Render Dashboard Results
if st.session_state.signals:
    df = pd.DataFrame(st.session_state.signals)
    useful_df = df[df["category"] != "Irrelevant"]
    domain_count = df["domain"].nunique()

    # KPI Overview
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Pages Crawled", len(df))
    col2.metric("Permitted Domains", domain_count)
    col3.metric("Useful Signals Found", len(useful_df))
    top_theme = st.session_state.opportunities[0]["theme"] if st.session_state.opportunities else "N/A"
    col4.metric("Top Opportunity Theme", top_theme)

    st.divider()

    # Charts Row
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Signal Categories")
        cat_counts = df["category"].value_counts()
        st.bar_chart(cat_counts)

    with c2:
        st.subheader("Top Recurring Themes")
        if not useful_df.empty:
            theme_counts = useful_df["theme"].value_counts().head(8)
            st.bar_chart(theme_counts)
        else:
            st.info("No relevant themes extracted.")

    st.divider()

    # Top 5 Opportunity Briefs
    st.header("🏆 Top Ranked Opportunity Briefs")
    if not st.session_state.opportunities:
        st.warning("Not enough high-relevance signals to generate opportunity briefs.")
    else:
        for opp in st.session_state.opportunities:
            brief = opp["brief"]
            with st.expander(
                f"#{opp['rank']} — {opp['theme']} ({opp['category']}) | Score: {opp['opportunity_score']}/100 "
                f"({opp['source_count']} sources across {opp['domain_count']} domains)",
                expanded=(opp["rank"] == 1)
            ):
                b1, b2 = st.columns(2)
                with b1:
                    st.markdown(f"**What is happening & who needs it:**\n{brief['what_is_happening']}")
                    st.markdown(f"**Why it matters now:**\n{brief['why_it_matters_now']}")
                with b2:
                    st.markdown(f"**Product / Business Angle:**\n{brief['product_or_business_angle']}")
                    st.markdown(f"**Validation Next Step:**\n{brief['validation_next_step']}")

                st.markdown("**Supporting Verbatim Evidence:**")
                for ev in brief.get("supporting_evidence", []):
                    st.markdown(f"- *\"{ev['evidence']}\"* — [{ev['domain']}]({ev['url']})")

    st.divider()

    # Filterable Evidence Table + Detail Inspector
    st.header("🔍 Signal Explorer & Evidence Inspector")
    f1, f2 = st.columns([1, 1])
    with f1:
        selected_cats = st.multiselect(
            "Filter by Category",
            options=df["category"].unique().tolist(),
            default=[c for c in df["category"].unique() if c != "Irrelevant"]
        )
    with f2:
        min_rel = st.slider("Minimum Relevance Score", 0, 100, 30)

    filtered_df = df[
        (df["category"].isin(selected_cats)) &
        (df["relevance_score"] >= min_rel)
    ].sort_values(by="relevance_score", ascending=False)

    st.dataframe(
        filtered_df[[
            "category", "theme", "relevance_score", "urgency_score",
            "confidence_score", "summary", "domain", "url"
        ]],
        column_config={
            "url": st.column_config.LinkColumn("Source URL"),
            "relevance_score": st.column_config.ProgressColumn("Relevance", min_value=0, max_value=100, format="%d"),
            "urgency_score": st.column_config.ProgressColumn("Urgency", min_value=0, max_value=100, format="%d"),
        },
        use_container_width=True,
        hide_index=True
    )

    # Detail View Selector
    if not filtered_df.empty:
        st.subheader("📄 Evidence & AI Reasoning Detail View")
        selected_title = st.selectbox(
            "Select a finding to inspect verbatim evidence and scoring rationale:",
            options=filtered_df["title"].tolist()
        )
        row = filtered_df[filtered_df["title"] == selected_title].iloc[0]
        st.info(f"**Verbatim Evidence (≤30 words):** \"{row['evidence']}\"")
        st.markdown(f"**AI Scoring Reasoning:** {row['reasoning']}")
        st.markdown(f"**Source:** [{row['url']}]({row['url']}) | **Crawled:** {row['crawl_date']}")

    st.divider()

    # Export Section
    st.subheader("📥 Export Findings")
    ex1, ex2 = st.columns(2)
    with ex1:
        csv_data = filtered_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download Signals (CSV)",
            data=csv_data,
            file_name="web_signals_export.csv",
            mime="text/csv",
            use_container_width=True
        )
    with ex2:
        export_payload = {
            "topic": st.session_state.current_topic,
            "opportunities": st.session_state.opportunities,
            "signals": filtered_df.to_dict(orient="records")
        }
        st.download_button(
            "Download Full Report (JSON)",
            data=json.dumps(export_payload, indent=2).encode("utf-8"),
            file_name="web_signal_hunter_report.json",
            mime="application/json",
            use_container_width=True
        )