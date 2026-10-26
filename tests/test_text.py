from app.text import relevant_excerpt, source_context


def test_relevant_excerpt_prefers_matching_paragraphs():
    markdown = (
        "Intro about nothing.\n\n"
        "The dental scheduling tool costs $149 per month.\n\n"
        "An unrelated paragraph about hiring.\n\n"
        "Churn stays below two percent for dental clinics."
    )
    excerpt = relevant_excerpt("What does the dental tool cost?", markdown, limit=120)
    assert "$149" in excerpt
    assert "hiring" not in excerpt


def test_source_context_keeps_full_short_document():
    markdown = "A short page."
    assert source_context("question", markdown, limit=100) == markdown


def test_source_context_truncates_long_documents():
    markdown = ("Filler paragraph.\n\n" * 50) + "The answer mentions zebras.\n\n" + ("More filler.\n\n" * 50)
    context = source_context("zebras", markdown, limit=400)
    assert len(context) <= 500
    assert "zebras" in context
    assert "PASSAGES MOST RELEVANT" in context
