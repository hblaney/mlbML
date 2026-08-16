"""Regression: never manufacture High/Elite to fill a daily quota."""

from __future__ import annotations

from gbm_confidence import assign_daily_confidence


def test_no_high_quota_without_gates() -> None:
    board = [
        {
            "pickProbability": 0.60,
            "rawPickProbability": 0.60,
            "starterCertain": True,
            "homeMoneyline": -140,
            "awayMoneyline": 120,
            "marketAgrees": True,
            "modelEdge": 0.02,
            "eraDiff": 0.2,  # below High era gate
            "formEdge": 0.3,
            "explanation": [],
        },
        {
            "pickProbability": 0.59,
            "rawPickProbability": 0.59,
            "starterCertain": True,
            "homeMoneyline": None,
            "awayMoneyline": None,
            "marketAgrees": None,
            "modelEdge": 0.0,
            "eraDiff": 1.0,
            "formEdge": 0.3,
            "explanation": [],
        },
        {
            "pickProbability": 0.58,
            "rawPickProbability": 0.58,
            "starterCertain": True,
            "homeMoneyline": -110,
            "awayMoneyline": -110,
            "marketAgrees": False,
            "modelEdge": 0.05,
            "eraDiff": 1.5,
            "formEdge": 0.2,
            "explanation": [],
        },
    ]
    assign_daily_confidence(board)
    assert all(r["confidence"] not in ("High", "Elite") for r in board)
    # First row is a lean (price-supported, soft ERA).
    assert board[0]["confidence"] == "Medium"
    assert board[0]["betAction"] == "lean"


def test_high_requires_full_gates() -> None:
    board = [
        {
            "pickProbability": 0.58,
            "rawPickProbability": 0.58,
            "starterCertain": True,
            "homeMoneyline": -130,
            "awayMoneyline": 110,
            "marketAgrees": True,
            "modelEdge": 0.04,
            "eraDiff": 0.6,
            "formEdge": 0.15,
            "explanation": [],
        }
    ]
    assign_daily_confidence(board)
    assert board[0]["confidence"] == "High"
    assert board[0]["betAction"] == "bet"


def test_no_high_without_form_or_market_or_edge() -> None:
    board = [
        {
            "pickProbability": 0.66,
            "rawPickProbability": 0.66,
            "starterCertain": True,
            "homeMoneyline": -150,
            "awayMoneyline": 130,
            "marketAgrees": False,
            "modelEdge": 0.08,
            "eraDiff": 1.5,
            "formEdge": 0.2,
            "explanation": [],
        },
        {
            "pickProbability": 0.66,
            "rawPickProbability": 0.66,
            "starterCertain": True,
            "homeMoneyline": -150,
            "awayMoneyline": 130,
            "marketAgrees": True,
            "modelEdge": 0.005,
            "eraDiff": 1.5,
            "formEdge": 0.2,
            "explanation": [],
        },
        {
            "pickProbability": 0.66,
            "rawPickProbability": 0.66,
            "starterCertain": True,
            "homeMoneyline": -150,
            "awayMoneyline": 130,
            "marketAgrees": True,
            "modelEdge": 0.05,
            "eraDiff": 1.5,
            "formEdge": 0.0,  # below High form gate (0.1)
            "explanation": [],
        },
    ]
    assign_daily_confidence(board)
    assert all(r["confidence"] != "High" and r["confidence"] != "Elite" for r in board)
    assert board[2]["confidence"] == "Medium"  # price-supported lean
    assert board[2]["betAction"] == "lean"


if __name__ == "__main__":
    test_no_high_quota_without_gates()
    test_high_requires_full_gates()
    test_no_high_without_form_or_market_or_edge()
    print("ok")
