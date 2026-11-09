"""Test verification for login page UI rendering and HTML structure."""
import re
from unittest.mock import MagicMock, patch
import pytest

from frontend.iqui.views import auth
from frontend.iqui import components as C


def test_auth_html_compaction_and_rendering():
    """Verify that all HTML emitted in auth.py has no leading whitespace or blank lines that could cause CommonMark code block parsing."""
    markdown_calls = []

    def mock_markdown(s: str, **kwargs):
        markdown_calls.append(s)

    with patch("streamlit.markdown", side_effect=mock_markdown):
        with patch("streamlit.columns") as mock_cols:
            mock_cols.return_value = (MagicMock(), MagicMock())
            with patch("streamlit.container"):
                with patch("streamlit.selectbox", return_value="Recruiter"):
                    with patch("streamlit.radio", return_value="Log In"):
                        with patch("streamlit.text_input", return_value=""):
                            with patch("streamlit.button", return_value=False):
                                with patch("streamlit.expander"):
                                    auth.render()

    assert len(markdown_calls) >= 3, f"Expected CSS, branding HTML, and card header HTML to be passed to st.markdown, got {len(markdown_calls)}."

    for chunk in markdown_calls:
        # Verify that chunk has been compacted with no newlines that could trigger markdown code block
        assert "\n" not in chunk, f"HTML chunk must be compacted to single line to prevent markdown code block formatting: {repr(chunk[:80])}"
        assert not chunk.startswith("    "), "HTML chunk must not start with 4 spaces (code block trigger)."

    # Find the branding chunk
    brand_chunks = [c for c in markdown_calls if "Interview" in c and "IQ" in c]
    assert len(brand_chunks) >= 1, "Expected branding HTML chunk."
    brand_chunk = brand_chunks[0]

    assert "Interview<span style=\"color: #3B82F6;\">IQ</span>" in brand_chunk
    assert "Smarter Hiring." in brand_chunk
    assert "Better Talent." in brand_chunk

    # Verify exactly 3 feature cards
    features = re.findall(r'<div class="iq-brand-feature">', brand_chunk)
    assert len(features) == 3, f"Expected exactly 3 feature sections, found {len(features)}"

    # Verify feature titles
    assert "Autonomous Multi-Turn AI Interviews" in brand_chunk
    assert "Evidence-Based LLM Candidate Matching" in brand_chunk
    assert "Anti-Proxy" in brand_chunk

    # Verify trust indicators
    assert "Enterprise Data Security" in brand_chunk
    assert "Sub-second AI Evaluation" in brand_chunk
    assert "100% Bias-Free Scoring" in brand_chunk

    # Verify background image data URI is populated
    bg_uri = auth._get_bg_data_uri()
    assert bg_uri.startswith("data:image/jpeg;base64,"), "Background image must be base64 data URI."
    assert len(bg_uri) > 1000, "Background image URI must contain real image bytes."
