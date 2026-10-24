"""Tests for form_fixes.py."""

import sys
from pathlib import Path

from opencc import OpenCC

sys.path.insert(0, str(Path(__file__).parent))
import form_fixes as ff

T2S = OpenCC("t2s")


def test_fix_form_rules() -> None:
    assert ff.fix_form("cmn", "游戏 规则", T2S) == "游戏规则"
    assert ff.fix_form("cmn", "４月", T2S) == "4月"
    assert ff.fix_form("cmn", "開齋節", T2S) == "开斋节"
    # simplified only into rare characters: kept
    assert ff.fix_form("cmn", "鰤", T2S) == "鰤"
    # full-width punctuation is normal in Chinese
    assert ff.fix_form("cmn", "阿波里耐，纪尧姆", T2S) == "阿波里耐，纪尧姆"
    assert ff.fix_form("ja", "ＶＩＰ") == "VIP"
    assert ff.fix_form("ja", "跡取リ") == "跡取り"
    assert ff.fix_form("ja", "中央ハ") == "中央ハ"
    assert ff.fix_form("zsm", "banjir ") == "banjir"
    assert ff.fix_form("zsm", "banjir + KN") == "banjir + KN"


def test_update_adds_renames_and_fixes_add_rows() -> None:
    # Arrange
    rows = [{"synset_id": "cow-1-n", "lemma": "游戏 规则", "action": "remove"},
            {"synset_id": "cow-2-n", "lemma": "猛烈 地", "action": "add"}]
    senses = [("cow-1-n", "游戏 规则"), ("cow-3-n", "游戏 规则"), ("cow-3-n", "狗")]

    # Act
    out, n = ff.update("cmn", senses, rows, "d", T2S)

    # Assert
    assert out[1]["lemma"] == "猛烈地"
    assert [(r["synset_id"], r["new_lemma"], r["reason"]) for r in out[2:]] == [
        ("cow-3-n", "游戏规则", "spaces between Han characters")]
    assert (n["rename added"], n["add fixed"]) == (1, 1)
