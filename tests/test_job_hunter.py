"""
Unit tests for Job Hunter core scraper, resume matcher, and salary filters.
"""

import pytest
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "scripts"))

from scripts.salary_filter import check_salary_floor
from scripts.question_answerer import fallback_answer
from scripts.resume_selector import ResumeSelector


def test_salary_floor():
    # Roles clearly below 30 LPA should be flagged
    is_below, reason = check_salary_floor("We offer a competitive compensation of 15 to 22 LPA.")
    assert is_below is True
    assert "below candidate floor" in reason

    # Roles clearly above floor should pass
    is_below_high, _ = check_salary_floor("Total compensation package of 50 to 65 LPA based on experience.")
    assert is_below_high is False


def test_fallback_answers():
    qa_mock = {
        "current_notice_period": "30 Days",
        "location": "Bengaluru, India",
        "current_company": "Tech Corp",
        "current_title": "Director of Strategy"
    }
    ans_notice = fallback_answer("What is your notice period?", qa_mock)
    assert "30 Days" in ans_notice

    ans_location = fallback_answer("Where are you currently located?", qa_mock)
    assert "Bengaluru, India" in ans_location


def test_resume_selector():
    selector = ResumeSelector(resumes_dir=str(BASE_DIR / "resumes"))
    assert len(selector.variants) > 0
    # Evaluate a sample Strategy job description
    sample_jd = "Looking for a Chief of Staff to partner with executive leadership, manage operating rhythms, and drive strategic initiatives."
    match = selector.evaluate_fit("Chief of Staff", sample_jd)
    assert match["fit_score"] > 0
    assert match["selected_resume"] is not None
