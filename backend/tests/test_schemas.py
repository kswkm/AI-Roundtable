import pytest

from roundtable.debate.schemas import FinalResult, JudgeEval, Opinion, ReviewedOpinion, parse_json_model

OPINION = '{"position": "찬성", "reasons": ["r"], "conditions": [], "confidence": 0.8}'


def test_parse_plain_json():
    assert parse_json_model(OPINION, Opinion).position == "찬성"


def test_parse_handles_fenced_and_wrapped_json():
    fenced = f"```json\n{OPINION}\n```"
    wrapped = f"제 의견은 다음과 같습니다.\n{OPINION}\n이상입니다."
    assert parse_json_model(fenced, Opinion).confidence == 0.8
    assert parse_json_model(wrapped, Opinion).position == "찬성"


def test_parse_rejects_missing_json_and_missing_fields():
    with pytest.raises(ValueError):
        parse_json_model("JSON이 없습니다", Opinion)
    with pytest.raises(ValueError):
        parse_json_model('{"position": "찬성"}', Opinion)
    with pytest.raises(ValueError):
        parse_json_model('{"position": "찬성", "reasons": [}', Opinion)


def test_confidence_percent_is_normalized():
    assert parse_json_model('{"position": "p", "reasons": [], "confidence": 85}', Opinion).confidence == 0.85
    assert parse_json_model('{"position": "p", "reasons": [], "confidence": 1}', Opinion).confidence == 1.0
    with pytest.raises(ValueError):
        parse_json_model('{"position": "p", "reasons": [], "confidence": 150}', Opinion)


def test_reviewed_opinion_is_an_opinion():
    reviewed = parse_json_model(
        '{"position": "p", "reasons": [], "confidence": 0.5, "changes": "유지", "rebuttals": ["b"]}',
        ReviewedOpinion,
    )
    assert isinstance(reviewed, Opinion)
    assert Opinion.model_validate(reviewed.model_dump()).position == "p"


def test_judge_eval_and_final_result_reject_unknown_values():
    with pytest.raises(ValueError):
        parse_json_model('{"status": "done"}', JudgeEval)
    with pytest.raises(ValueError):
        parse_json_model('{"final_opinion": "x", "grade": "majority", "key_reasons": []}', FinalResult)
