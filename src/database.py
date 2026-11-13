import sqlite3
import json
from typing import List, Dict, Any
from src.config import DB_PATH


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_topic TEXT,
            url TEXT,
            domain TEXT,
            title TEXT,
            crawl_date TEXT,
            category TEXT,
            theme TEXT,
            summary TEXT,
            evidence TEXT,
            relevance_score INTEGER,
            urgency_score INTEGER,
            confidence_score INTEGER,
            reasoning TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_topic TEXT,
            rank INTEGER,
            theme TEXT,
            category TEXT,
            opportunity_score REAL,
            source_count INTEGER,
            domain_count INTEGER,
            brief_json TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_run_results(topic: str, signals: List[Dict[str, Any]], opportunities: List[Dict[str, Any]]):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Clear previous data for the exact same topic to keep runs clean
    c.execute("DELETE FROM signals WHERE run_topic = ?", (topic,))
    c.execute("DELETE FROM opportunities WHERE run_topic = ?", (topic,))

    for s in signals:
        c.execute("""
            INSERT INTO signals (
                run_topic, url, domain, title, crawl_date, category, theme,
                summary, evidence, relevance_score, urgency_score, confidence_score, reasoning
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            topic, s["url"], s["domain"], s["title"], s["crawl_date"],
            s["category"], s["theme"], s["summary"], s["evidence"],
            s["relevance_score"], s["urgency_score"], s["confidence_score"], s["reasoning"]
        ))

    for opp in opportunities:
        c.execute("""
            INSERT INTO opportunities (
                run_topic, rank, theme, category, opportunity_score,
                source_count, domain_count, brief_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            topic, opp["rank"], opp["theme"], opp["category"],
            opp["opportunity_score"], opp["source_count"], opp["domain_count"],
            json.dumps(opp["brief"])
        ))

    conn.commit()
    conn.close()