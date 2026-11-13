from collections import defaultdict, Counter
from typing import List, Dict, Any
from src.analyzer import SignalAnalyzer


def rank_opportunities(
    topic: str,
    signals: List[Dict[str, Any]],
    analyzer: SignalAnalyzer,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Transparent Opportunity Scoring Formula:
    Base Quality = (0.40 * Avg_Relevance) + (0.35 * Avg_Urgency) + (0.25 * Avg_Confidence)
    Evidence Multiplier = 1 + 0.15 * ln(Source_Count) + 0.10 * (Unique_Domains - 1)
    Opportunity Score = min(100, round(Base Quality * Evidence Multiplier, 2))
    """
    import math

    useful = [s for s in signals if s["category"] != "Irrelevant" and s["relevance_score"] >= 30]
    if not useful:
        return []

    # Group by normalized theme
    clusters: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for s in useful:
        norm_theme = s["theme"].strip().title()
        clusters[norm_theme].append(s)

    scored_clusters = []
    for theme, items in clusters.items():
        source_count = len(items)
        unique_domains = len({item["domain"] for item in items})
        avg_rel = sum(i["relevance_score"] for i in items) / source_count
        avg_urg = sum(i["urgency_score"] for i in items) / source_count
        avg_conf = sum(i["confidence_score"] for i in items) / source_count

        dominant_category = Counter(i["category"] for i in items).most_common(1)[0][0]

        base_quality = (0.40 * avg_rel) + (0.35 * avg_urg) + (0.25 * avg_conf)
        multiplier = 1.0 + (0.15 * math.log(source_count)) + (0.10 * max(0, unique_domains - 1))
        opp_score = min(100.0, round(base_quality * multiplier, 2))

        scored_clusters.append({
            "theme": theme,
            "category": dominant_category,
            "opportunity_score": opp_score,
            "source_count": source_count,
            "domain_count": unique_domains,
            "avg_relevance": round(avg_rel, 1),
            "avg_urgency": round(avg_urg, 1),
            "avg_confidence": round(avg_conf, 1),
            "items": sorted(items, key=lambda x: x["relevance_score"], reverse=True)
        })

    scored_clusters.sort(key=lambda x: x["opportunity_score"], reverse=True)
    top_clusters = scored_clusters[:top_k]

    ranked_results = []
    for idx, cluster in enumerate(top_clusters, start=1):
        brief = analyzer.generate_opportunity_brief(
            topic=topic,
            theme=cluster["theme"],
            category=cluster["category"],
            supporting_signals=cluster["items"]
        )
        ranked_results.append({
            "rank": idx,
            "theme": cluster["theme"],
            "category": cluster["category"],
            "opportunity_score": cluster["opportunity_score"],
            "source_count": cluster["source_count"],
            "domain_count": cluster["domain_count"],
            "avg_relevance": cluster["avg_relevance"],
            "avg_urgency": cluster["avg_urgency"],
            "avg_confidence": cluster["avg_confidence"],
            "brief": brief
        })

    return ranked_results