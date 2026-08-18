"""Число реплик человека у сессии. Запуск: python3 tests/test_prompt_count.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()


def human(text):
    return {"type": "user", "timestamp": "2026-08-18T10:00:00Z",
            "message": {"role": "user", "content": text}}


def tool_result():
    # Под `type: user` лежит далеко не только человек: замер в самом
    # агрегаторе — 109 записей `user` на 5 человеческих.
    return {"type": "user", "toolUseResult": {"stdout": "ok"},
            "message": {"role": "user", "content": [{"type": "tool_result"}]}}


def write(path, records, mode="w"):
    with open(path, mode, encoding="utf-8") as fh:
        for o in records:
            fh.write(json.dumps(o) + "\n")


def test_only_human_messages_count():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.jsonl")
        write(p, [human("раз"), tool_result(), human("два"),
                  {"type": "assistant", "message": {"content": []}}])
        assert CC["count_prompts"](p, 0, 0)[0] == 2


def test_the_count_continues_from_where_it_stopped():
    # Транскрипт только дописывают, поэтому пересчитывать прочитанное незачем.
    # Ради этого всё и делается: полный проход по ста сессиям — 0.45 с, и
    # платить его на каждом опросе нельзя.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.jsonl")
        write(p, [human("раз")])
        first, at = CC["count_prompts"](p, 0, 0)
        assert (first, at) == (1, os.path.getsize(p))
        write(p, [human("два"), human("три")], mode="a")
        second, at2 = CC["count_prompts"](p, at, first)
        assert second == 3, second
        assert at2 == os.path.getsize(p)


def test_a_half_written_line_is_not_counted_and_not_skipped():
    # Файл читается в тот момент, когда агент его пишет: хвост бывает без
    # перевода строки. Досчитав такую строку, счёт бы завысили; пропустив её
    # смещением — потеряли бы реплику навсегда, потому что второй раз её никто
    # не прочтёт.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.jsonl")
        write(p, [human("раз")])
        whole = os.path.getsize(p)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(human("недописанная"))[:20])
        count, at = CC["count_prompts"](p, 0, 0)
        assert count == 1, count
        assert at == whole, at
        # Дописали остаток — реплика досчитывается со следующего захода.
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(human("недописанная"))[20:] + "\n")
        assert CC["count_prompts"](p, at, count)[0] == 2


def test_a_missing_file_keeps_what_was_counted():
    # Транскрипт мог уехать вместе с чисткой. Обнулять счёт из-за этого не
    # надо: строка списка ещё живёт, и ноль в колонке читался бы как «человек
    # тут ни разу ничего не спросил».
    assert CC["count_prompts"]("/nonexistent-transcript.jsonl", 10, 7) == (7, 10)


def test_the_memo_recounts_a_truncated_file_from_scratch():
    # Уменьшение размера — единственная наблюдаемая подпись подмены файла, и
    # то же правило действует у gist и у бумаг: чужой счёт пережил бы подмену
    # и врал бы молча.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.jsonl")
        write(p, [human("раз")])
        cache = {p: {"mtime": 1.0, "title": "t", "doing": "d", "turnAt": 0,
                     "gist": "g", "gistDone": True, "size": 10 ** 6,
                     "prompts": 42, "countedTo": 10 ** 6}}
        got = CC["facts_for"](p, 2.0, cache,
                              tail=lambda q: ("t", "d", 0, {}), head=lambda q: "g")
        assert got["prompts"] == 1, got
        assert got["countedTo"] == os.path.getsize(p), got


def test_the_memo_keeps_the_count_when_the_file_did_not_change():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.jsonl")
        write(p, [human("раз")])
        cache = {p: {"mtime": 2.0, "title": "t", "doing": "d", "turnAt": 0,
                     "gist": "g", "gistDone": True, "size": os.path.getsize(p),
                     "prompts": 5, "countedTo": os.path.getsize(p)}}
        got = CC["facts_for"](p, 2.0, cache,
                              tail=lambda q: ("t", "d", 0, {}), head=lambda q: "g")
        assert got["prompts"] == 5, got


def test_dump_counts_too_so_the_memo_stays_whole():
    # Памятка у режимов общая, и запись без счёта, положенная дампом, читалась
    # бы --state как полная — у простаивающей сессии mtime больше не сдвинется
    # никогда. Ровно эта болезнь уже описана у `gist`.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.jsonl")
        write(p, [human("раз"), human("два")])
        got = CC["facts_for"](p, 2.0, {}, tail=lambda q: ("t", "d", 0, {}),
                              head=lambda q: "g", want_gist=False)
        assert got["prompts"] == 2, got


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
