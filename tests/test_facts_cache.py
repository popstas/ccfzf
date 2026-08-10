"""Памятка фактов о транскриптах. Запуск: python3 tests/test_facts_cache.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

P = "/d/a1.jsonl"


def counting(title="T", doing="D", gist="G"):
    calls = {"tail": 0, "head": 0}

    def tail(path):
        calls["tail"] += 1
        return title, doing

    def head(path):
        calls["head"] += 1
        return gist

    return calls, tail, head


def test_a_hit_recomputes_nothing():
    calls, tail, head = counting()
    cache = {P: {"mtime": 100.0, "title": "T", "doing": "D",
                 "gist": "G", "gistDone": True}}
    got = CC["facts_for"](P, 100.0, cache, tail=tail, head=head)
    assert got == cache[P], got
    assert calls == {"tail": 0, "head": 0}, calls


def test_a_changed_file_recomputes_the_tail():
    calls, tail, head = counting()
    cache = {P: {"mtime": 100.0, "title": "old", "doing": "old",
                 "gist": "G", "gistDone": True}}
    got = CC["facts_for"](P, 200.0, cache, tail=tail, head=head)
    assert got["title"] == "T" and got["doing"] == "D", got
    assert calls["tail"] == 1, calls


def test_a_known_gist_survives_any_change_to_the_file():
    # Первый промпт сессии неизменен — ключевать его по mtime незачем. Это
    # 165 мс из 320 на двухстах сессиях, и уходят они даже у тех сессий,
    # которые пишутся прямо сейчас.
    calls, tail, head = counting()
    cache = {P: {"mtime": 100.0, "title": "old", "doing": "old",
                 "gist": "первый промпт", "gistDone": True}}
    got = CC["facts_for"](P, 999.0, cache, tail=tail, head=head)
    assert got["gist"] == "первый промпт", got
    assert calls["head"] == 0, calls


def test_an_empty_gist_is_retried_while_the_file_is_small():
    calls, tail, head = counting(gist="")
    got = CC["facts_for"](P, 100.0, {}, tail=tail, head=head,
                          size_of=lambda p: 10)
    assert calls["head"] == 1, calls
    assert got["gist"] == "" and got["gistDone"] is False, got


def test_an_empty_gist_stops_being_retried_past_the_head_limit():
    # head_gist дальше HEAD_LIMIT и не смотрит, значит ответ измениться уже
    # не может — спрашивать бессмысленно до конца жизни файла.
    calls, tail, head = counting(gist="")
    got = CC["facts_for"](P, 100.0, {}, tail=tail, head=head,
                          size_of=lambda p: CC["HEAD_LIMIT"] + 1)
    assert got["gistDone"] is True, got
    calls2, tail2, head2 = counting(gist="")
    again = CC["facts_for"](P, 200.0, {P: got}, tail=tail2, head=head2,
                            size_of=lambda p: CC["HEAD_LIMIT"] + 1)
    assert calls2["head"] == 0, calls2
    assert again["gistDone"] is True, again


def test_the_title_is_stored_cleaned():
    calls, tail, head = counting(title="  t\tt  ")
    got = CC["facts_for"](P, 100.0, {}, tail=tail, head=head)
    assert got["title"] == CC["clean"]("  t\tt  "), got


def test_a_broken_memo_reads_as_empty():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "facts.json")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("{ не json")
        assert CC["load_facts"](p) == {}, "рваный файл"
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"v": 999, "files": {P: {"mtime": 1}}}, fh)
        assert CC["load_facts"](p) == {}, "чужая версия"
        assert CC["load_facts"]("") == {}, "выключенная памятка"
        assert CC["load_facts"](os.path.join(tmp, "нет.json")) == {}, "нет файла"


def test_save_then_load_round_trips():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "sub", "facts.json")
        facts = {P: {"mtime": 100.0, "title": "T", "doing": "D",
                     "gist": "G", "gistDone": True}}
        CC["save_facts"](p, facts)
        assert CC["load_facts"](p) == facts, CC["load_facts"](p)


if __name__ == "__main__":
    fails = 0
    names = [n for n in globals() if n.startswith("test_")]
    for name in sorted(names):
        try:
            globals()[name]()
            print("ok   " + name)
        except AssertionError as e:
            fails += 1
            print("FAIL " + name + ": " + str(e))
    print("%d/%d passed" % (len(names) - fails, len(names)))
    sys.exit(1 if fails else 0)
