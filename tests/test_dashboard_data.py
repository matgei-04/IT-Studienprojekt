# Selbst erstellt – bitte prüfen und erklären können.
"""Tests für die reine Klassifikationslogik der Dashboard-Datenschicht."""

from app.data import classify_confidence


def test_high_score_is_automatic():
    assert classify_confidence(0.95) == "automatisch"
    assert classify_confidence(0.80) == "automatisch"


def test_medium_score_needs_review():
    assert classify_confidence(0.79) == "pruefung"
    assert classify_confidence(0.55) == "pruefung"


def test_low_score_is_unmatched():
    assert classify_confidence(0.54) == "nicht_zuordenbar"
    assert classify_confidence(0.0) == "nicht_zuordenbar"
