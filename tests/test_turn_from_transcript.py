"""Начало хода по транскрипту. Запуск: python3 tests/test_turn_from_transcript.py

Ход начинает сообщение человека, а не отметка хука: хук молчащий, перестал
писать — и ход застыл, тогда как сессия по-прежнему числится работающей.
Транскрипт — наблюдение, и врать ему нечем.

Цена этого правила — разбор: под `type: "user"` в транскрипте лежит далеко не
только человек. Замерено 2026-08-15 на живой сессии: 109 записей `user`, из них
человеческих 5. Приняв результат инструмента за реплику, ход считался бы от
последнего вызова grep — то есть не считался бы вовсе.
"""
import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

HUMAN_AT = 1785958000
TOOL_AT = 1785958900


def _stamp(at):
    return datetime.datetime.fromtimestamp(
        at, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _human(at, text="сделай так"):
    return {"type": "user", "timestamp": _stamp(at),
            "message": {"role": "user", "content": text}}


def _tool_result(at):
    """Ответ инструмента — тоже `user`, и это главная ловушка разбора."""
    return {"type": "user", "timestamp": _stamp(at), "toolUseResult": {"stdout": "ok"},
            "message": {"role": "user",
                        "content": [{"type": "tool_result", "content": "ok"}]}}


def _notification(at):
    """Уведомление о конце субагента. Форма снята с живой записи (2.1.233)."""
    return {"type": "user", "timestamp": _stamp(at), "isSidechain": False,
            "promptSource": "system", "origin": {"kind": "task-notification"},
            "message": {"role": "user",
                        "content": "<task-notification>\n<task-id>a22ef</task-id>\n"
                                   "<status>completed</status>\n</task-notification>"}}


def _slash_command(at):
    """Слэш-команда: обёртки в тексте есть, но набрал её человек."""
    return {"type": "user", "timestamp": _stamp(at),
            "message": {"role": "user",
                        "content": "<command-message>do</command-message>\n"
                                   "<command-name>/do</command-name>"}}


def _write(path, records):
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _tail(records):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "s.jsonl")
        _write(path, records)
        return CC["tail_facts"](path)


# ── Что считается сообщением человека ──────────────────────────────────────


def test_a_plain_user_message_is_human():
    assert CC["is_human_message"](_human(HUMAN_AT)) is True


def test_a_tool_result_is_not_human():
    assert CC["is_human_message"](_tool_result(TOOL_AT)) is False


def test_a_tool_result_block_without_the_pinned_field_is_not_human():
    # Вторая половина того же признака: результат бывает виден только со
    # стороны содержимого. Одного `toolUseResult` мало.
    o = {"type": "user", "timestamp": _stamp(TOOL_AT),
         "message": {"content": [{"type": "tool_result", "content": "ok"}]}}
    assert CC["is_human_message"](o) is False


def test_a_meta_record_is_not_human():
    # Служебные вставки самого Claude Code. Человек их не писал и не видел.
    o = _human(HUMAN_AT)
    o["isMeta"] = True
    assert CC["is_human_message"](o) is False


def test_a_sidechain_record_is_not_human():
    # Реплика субагенту: его позвал агент, а не человек, и ход человека она не
    # начинает.
    o = _human(HUMAN_AT)
    o["isSidechain"] = True
    assert CC["is_human_message"](o) is False


def test_a_task_notification_is_not_human():
    # Конец субагента приезжает в транскрипт записью `user` — не мета, не
    # сайдчейн, содержимое строкой, — и от реплики человека отличается только
    # своими полями. Пришло оно не от человека: работу закончил агент.
    assert CC["is_human_message"](_notification(TOOL_AT)) is False


def test_a_task_notification_without_the_new_field_is_not_human():
    # `promptSource` завёлся не сразу: на 583 уведомлениях в живых транскриптах
    # (замер 2026-08-16) `origin.kind` стоит у всех, а `promptSource` — у всех,
    # кроме трёх, записанных 2.1.159. Признака поэтому два, и это не запас: без
    # второго старый транскрипт разбирался бы по-прежнему неверно.
    o = _notification(TOOL_AT)
    del o["promptSource"]
    assert CC["is_human_message"](o) is False


def test_a_system_submission_of_an_unknown_kind_is_not_human():
    # Обратная половина той же пары: `promptSource: system` называет вставку
    # вообще, а не один её вид, и новый вид уведомления не потребует правки.
    o = _notification(TOOL_AT)
    del o["origin"]
    assert CC["is_human_message"](o) is False


def test_a_slash_command_is_still_human():
    # Отсев по обёрткам в тексте («начинается с <») забрал бы и слэш-команды, а
    # их набирает человек, и ход они начинают. Отсюда разбор по полям записи.
    assert CC["is_human_message"](_slash_command(HUMAN_AT)) is True


def test_an_assistant_record_is_not_human():
    assert CC["is_human_message"]({"type": "assistant", "timestamp": _stamp(HUMAN_AT)}) is False


def test_junk_does_not_crash_the_check():
    # Разбирается чужой файл: мусор обязан стоить себя, а не ответа.
    for junk in (None, "", 5, [], {"type": "user", "message": "не словарь"}):
        assert CC["is_human_message"](junk) is False


# ── Что достаёт из хвоста tail_facts ───────────────────────────────────────


def test_the_turn_starts_at_the_last_human_message():
    _, _, turn_at = _tail([
        _human(HUMAN_AT - 3600),
        _human(HUMAN_AT),
        {"type": "assistant", "timestamp": _stamp(HUMAN_AT + 5)},
        _tool_result(TOOL_AT),
    ])
    assert turn_at == HUMAN_AT, turn_at


def test_tool_results_after_the_human_do_not_move_the_turn():
    # Ровно то, ради чего разбор и заведён: длинный ход — это сотни записей
    # `user` от инструментов, и по ним ход был бы всегда «секунду назад».
    _, _, turn_at = _tail([_human(HUMAN_AT)] + [_tool_result(TOOL_AT + i) for i in range(20)])
    assert turn_at == HUMAN_AT, turn_at


def test_a_notification_after_the_human_does_not_move_the_turn():
    # Тот самый случай, ради которого разбор и правился (сессия a973,
    # 2026-08-15): человек спросил в 22:39, субагенты отчитывались до 23:19, и
    # ход датировался последним отчётом — «минуту назад» вместо сорока.
    _, _, turn_at = _tail([
        _human(HUMAN_AT),
        {"type": "assistant", "timestamp": _stamp(HUMAN_AT + 5)},
        _notification(TOOL_AT),
    ])
    assert turn_at == HUMAN_AT, turn_at


def test_a_tail_without_a_human_record_says_zero():
    # Ноль — «не нашлось», а не «хода не было»: длинный ход выталкивает реплику
    # человека за TAIL. Отличать одно от другого обязан вызывающий.
    _, _, turn_at = _tail([_tool_result(TOOL_AT), {"type": "assistant", "timestamp": _stamp(TOOL_AT)}])
    assert turn_at == 0, turn_at


def test_a_human_record_without_a_stamp_says_zero():
    o = _human(HUMAN_AT)
    del o["timestamp"]
    _, _, turn_at = _tail([o])
    assert turn_at == 0, turn_at


def test_the_title_and_doing_still_come_back():
    # Третье значение добавлено к двум прежним, а не вместо них: tail_facts
    # зовут и режим `sessions`, и памятка фактов.
    title, doing, turn_at = _tail([
        {"type": "custom-title", "customTitle": "моя сессия"},
        _human(HUMAN_AT, "почини сборку"),
    ])
    assert title == "моя сессия", title
    assert doing == "почини сборку", doing
    assert turn_at == HUMAN_AT, turn_at


def test_a_missing_file_costs_three_empties():
    assert CC["tail_facts"]("/nonexistent-transcript-for-tests.jsonl") == ("", "", 0.0)


# ── Памятка фактов ─────────────────────────────────────────────────────────


def test_the_turn_is_remembered_by_mtime_like_the_title():
    # Ход меняется только вместе с файлом, поэтому ключ mtime для него верен —
    # и поэтому же двухсот лишних чтений хвоста не появляется.
    calls = {"n": 0}

    def tail(path):
        calls["n"] += 1
        return "T", "D", HUMAN_AT

    got = CC["facts_for"]("/d/a.jsonl", 100.0, {}, tail=tail,
                          head=lambda p: "G", size_of=lambda p: 10)
    assert got["turnAt"] == HUMAN_AT, got
    hit = CC["facts_for"]("/d/a.jsonl", 100.0, {"/d/a.jsonl": got}, tail=tail,
                          head=lambda p: "G", size_of=lambda p: 10)
    assert hit["turnAt"] == HUMAN_AT, hit
    assert calls["n"] == 1, calls


def test_a_changed_file_recomputes_the_turn():
    def tail_new(path):
        return "T", "D", HUMAN_AT + 500

    old = {"/d/a.jsonl": {"mtime": 100.0, "title": "T", "doing": "D",
                          "turnAt": HUMAN_AT, "gist": "G", "gistDone": True}}
    got = CC["facts_for"]("/d/a.jsonl", 200.0, old, tail=tail_new,
                          head=lambda p: "G", size_of=lambda p: 10)
    assert got["turnAt"] == HUMAN_AT + 500, got


def test_the_facts_version_was_bumped_for_the_new_field():
    # Иначе памятка прошлой версии отдавала бы записи без `turnAt` как полные,
    # и ход у простаивающей сессии не появился бы никогда: mtime у неё больше
    # не сдвинется. Ровно та ошибка, за которую уже заплачено на `gist`.
    #
    # Второй раз версия поднята за то же самое, но по другому поводу: поле
    # осталось, изменилось его значение (отчёт субагента ход больше не
    # начинает), а неверное значение лежит в памятке под тем же ключом.
    assert CC["FACTS_VERSION"] >= 4, CC["FACTS_VERSION"]


# ── Второй, широкий хвост ──────────────────────────────────────────────────


def _padded(records, pad_to):
    """Транскрипт, раздутый вызовами инструментов до нужного размера."""
    out = list(records)
    filler = "x" * 4000
    while True:
        blob = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out)
        if len(blob.encode("utf-8")) >= pad_to:
            return out
        out.append({"type": "user", "timestamp": _stamp(TOOL_AT),
                    "toolUseResult": {"stdout": filler},
                    "message": {"content": [{"type": "tool_result", "content": filler}]}})


def test_a_human_message_past_the_narrow_tail_is_still_found():
    # Ровно замеренный случай: реплика человека дальше TAIL, но ближе
    # TURN_TAIL. Без второго прохода правило работало бы у простаивающих
    # сессий и молчало у работающих — то есть у тех, ради которых заведено.
    records = _padded([_human(HUMAN_AT)], CC["TAIL"] + 100 * 1024)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "s.jsonl")
        _write(path, records)
        assert os.path.getsize(path) > CC["TAIL"]
        assert CC["tail_facts"](path)[2] == HUMAN_AT


def test_a_human_message_past_the_wide_tail_says_zero():
    # Предел есть, и он назван: ход длиннее TURN_TAIL по-прежнему датируется
    # отметкой хука. Врать про «секунду назад» хуже, чем откатиться.
    records = _padded([_human(HUMAN_AT)], CC["TURN_TAIL"] + 100 * 1024)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "s.jsonl")
        _write(path, records)
        assert os.path.getsize(path) > CC["TURN_TAIL"]
        assert CC["tail_facts"](path)[2] == 0


def test_the_wide_tail_is_wider_than_the_narrow_one():
    # Равные константы означали бы второй проход, который ничего не добавляет,
    # и цену без ответа.
    assert CC["TURN_TAIL"] > CC["TAIL"], (CC["TURN_TAIL"], CC["TAIL"])


# Тот же хвост, что у остальных файлов в tests/. Без него запуск, обещанный
# первой строкой этого файла, молча ничего не проверяет и выходит с нулём — и
# ровно так уведомление субагента дожило до живого пикера.
TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print("ok   %s" % t.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL %s: %s" % (t.__name__, e))
    print("%d/%d passed" % (len(TESTS) - failed, len(TESTS)))
    sys.exit(1 if failed else 0)
