import pytest

from mapper.llm import _choice_text, extract_json_object, normalize_mapping_answer


def test_choice_text_reads_content():
    data = {"choices": [{"message": {"content": '{"mapping":[0]}'}, "finish_reason": "stop"}]}
    assert '"mapping"' in _choice_text(data)


def test_choice_text_reads_mapping_from_reasoning():
    data = {
        "choices": [
            {
                "finish_reason": "length",
                "message": {
                    "content": None,
                    "reasoning": 'thoughts...\n{"mapping":[1,0],"bond_changes":{"broken":[],"formed":[]}}',
                },
            }
        ]
    }
    text = _choice_text(data)
    assert normalize_mapping_answer(extract_json_object(text))["mapping"] == [1, 0]


def test_choice_text_rejects_empty_with_hint():
    data = {
        "choices": [
            {
                "finish_reason": "length",
                "native_finish_reason": "MAX_TOKENS",
                "message": {"content": None, "reasoning": None},
            }
        ]
    }
    with pytest.raises(ValueError, match="no content"):
        _choice_text(data)


def test_extract_json_object_rejects_none():
    with pytest.raises(ValueError, match="empty"):
        extract_json_object(None)


def test_normalize_mapping_answer_aliases():
    out = normalize_mapping_answer({"atom_mapping": [1, 0], "confidence": 0.8})
    assert out["mapping"] == [1, 0]
    assert out["bond_changes"]["broken"] == []


def test_normalize_mapping_dict():
    out = normalize_mapping_answer({"mapping": {"0": 2, "1": 0, "2": 1}})
    assert out["mapping"] == [2, 0, 1]
