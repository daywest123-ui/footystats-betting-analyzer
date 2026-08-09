from open_web_intelligence import aggregate


def test_aggregate_empty():
    result = aggregate([])
    assert result["mentions"] == 0
    assert "web_data_unavailable" in result["risk_flags"]


def test_aggregate_scores():
    from open_web_intelligence import WebMention
    result = aggregate([
        WebMention("a", "Strong win", "https://example.com", text="favorite and strong"),
        WebMention("b", "Injury doubt", "https://example.org", text="injury and suspended"),
    ])
    assert result["mentions"] == 2
    assert -1 <= result["web_score"] <= 1
