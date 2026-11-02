import pytest

from app.services.resume_parser import ResumeParseError, parse_profile, parse_resume
from tests.helpers import SAMPLE


def test_docx_resume_parsed():
    text, prof, _ = parse_resume("Aarav_Mehta.docx", (SAMPLE / "resumes" / "Aarav_Mehta.docx").read_bytes())
    assert prof.name == "Aarav Mehta"
    assert prof.email == "aarav.mehta@example.com"
    assert "python" in prof.skills and "fastapi" in prof.skills
    assert prof.experience_years >= 4
    assert "Kafka" in text


def test_pdf_resume_parsed():
    text, prof, _ = parse_resume("Priya_Nair.pdf", (SAMPLE / "resumes" / "Priya_Nair.pdf").read_bytes())
    assert prof.name == "Priya Nair"
    assert "Mentored two junior developers" in text


def test_unsupported_and_empty_and_tiny_files():
    with pytest.raises(ResumeParseError):
        parse_resume("cv.exe", b"MZ....")
    with pytest.raises(ResumeParseError):
        parse_resume("cv.pdf", b"")
    with pytest.raises(ResumeParseError):
        parse_resume("cv.txt", b"too short")


def test_corrupt_pdf_gives_clean_error():
    with pytest.raises(ResumeParseError):
        parse_resume("cv.pdf", b"%PDF-1.4 this is not really a pdf" * 5)


def test_profile_missing_fields_are_empty_not_crashing():
    p = parse_profile("some text without any contact details at all, just a long sentence here")
    assert p.email == "" and p.phone == "" and p.skills == []
    assert p.education == [] and p.experience == [] and p.projects == []


def test_experience_and_projects_extraction_and_education_cleanliness():
    text, prof, _ = parse_resume("Karan_Shah.docx", (SAMPLE / "resumes" / "Karan_Shah.docx").read_bytes())
    # Projects should extract the college project, not put it in education
    assert any("college project" in pr.lower() for pr in prof.projects)
    assert not any("college project" in ed.lower() for ed in prof.education)
    assert any("B.Tech" in ed for ed in prof.education)
    assert any("Intern" in ex for ex in prof.experience)

    text_a, prof_a, _ = parse_resume("Aarav_Mehta.docx", (SAMPLE / "resumes" / "Aarav_Mehta.docx").read_bytes())
    assert any("Senior Backend Engineer" in ex for ex in prof_a.experience)
    assert any("Re-architected" in pr or "microservices" in pr for pr in prof_a.projects)
