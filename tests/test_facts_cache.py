"""Памятка фактов о транскриптах. Запуск: python3 tests/test_facts_cache.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness

CC = harness.load()

P = "/d/a1.jsonl"


def counting(title="T", doing="D", gist="G", turn_at=0.0):
    calls = {"tail": 0, "head": 0}

    def tail(path):
        calls["tail"] += 1
        # Три значения, как у настоящей tail_facts: начало хода считается из
        # того же хвоста, что title и doing, и живёт в памятке по тому же
        # правилу — ключ mtime, промах пересчитывает.
        return title, doing, turn_at

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


def test_a_shrunk_file_invalidates_the_known_gist():
    # Транскрипт только дописывают — это допущение памятки, а не гарантия.
    # Если файл под тем же путём переписали заново (бэкап, сжатие истории,
    # id, отданный другой сессии), единственная видимая отсюда улика —
    # текущий размер стал меньше того, что лежит в памятке рядом с mtime.
    calls, tail, head = counting(gist="новый")
    cache = {P: {"mtime": 100.0, "title": "old", "doing": "old",
                 "gist": "старый", "gistDone": True, "size": 500}}
    got = CC["facts_for"](P, 200.0, cache, tail=tail, head=head,
                          size_of=lambda p: 100)
    assert calls["head"] == 1, calls
    assert got["gist"] == "новый", got
    assert got["size"] == 100, got


def test_a_freshly_found_gist_is_capped_at_two_hundred_chars():
    # Все потребители и так режут gist до 200 символов (doing режется тем же
    # пределом в tail_facts); хранить длиннее — плата за байты, которые
    # памятка целиком перезаписывает на каждый опрос со сдвинувшимся mtime.
    calls, tail, head = counting(gist="д" * 300)
    got = CC["facts_for"](P, 100.0, {}, tail=tail, head=head)
    assert len(got["gist"]) == 200, len(got["gist"])


def test_want_gist_false_never_calls_head():
    # Режим dump: gist в дамп не уезжает (DUMP_KEEP), платить за head_gist
    # незачем — ни разу, даже на холодной памятке без единой известной сессии.
    calls, tail, head = counting()
    got = CC["facts_for"](P, 100.0, {}, tail=tail, head=head, want_gist=False)
    assert calls["head"] == 0, calls
    assert "gist" not in got and "gistDone" not in got, got


def test_want_gist_false_never_writes_a_stale_gist_on_a_miss():
    # Критично: класть здесь gist="", gistDone=False было багом — --state
    # читает ту же памятку, попал бы по mtime и решил бы, что gist известен
    # и пуст, хотя dump его попросту не искал. Простаивающая сессия после
    # этого показывала бы человеку последний ответ агента вместо первого
    # промпта вечно, потому что mtime у неё больше не сдвинется. Отсутствие
    # ключей — единственный безопасный способ сказать «не искали», и dump не
    # переносит даже старый известный gist: у него нет своего способа
    # проверить его на усечение (см. test_a_shrunk_file_invalidates_...).
    calls, tail, head = counting()
    cache = {P: {"mtime": 100.0, "title": "old", "doing": "old",
                 "gist": "уже есть", "gistDone": True, "size": 5}}
    got = CC["facts_for"](P, 200.0, cache, tail=tail, head=head,
                          want_gist=False)
    assert calls["head"] == 0, calls
    assert "gist" not in got and "gistDone" not in got, got


def test_want_gist_false_hit_passes_the_known_gist_through_unmodified():
    # Настоящее попадание (mtime совпал, gist уже был известен) не портится:
    # dump ничего не пересчитывает и просто возвращает всю старую запись.
    calls, tail, head = counting()
    cache = {P: {"mtime": 100.0, "title": "T", "doing": "D",
                 "gist": "G", "gistDone": True, "size": 5}}
    got = CC["facts_for"](P, 100.0, cache, tail=tail, head=head,
                          want_gist=False)
    assert got == cache[P], got
    assert calls == {"tail": 0, "head": 0}, calls


def test_a_gist_unknown_record_is_a_half_miss_even_at_the_same_mtime():
    # Тот самый баг с находки 3: dump мог записать факты первым — title и
    # doing на этот mtime уже верны, а ключей gist/gistDone в записи нет
    # вовсе. Для звонка, которому gist нужен, совпавший mtime не должен
    # считаться попаданием: пересчитывать title/doing незачем (они не
    # изменились бы при том же mtime), а gist искать обязаны.
    calls, tail, head = counting(gist="первый промпт")
    cache = {P: {"mtime": 100.0, "title": "T", "doing": "D", "size": 5}}
    got = CC["facts_for"](P, 100.0, cache, tail=tail, head=head)
    assert calls["tail"] == 0, calls
    assert calls["head"] == 1, calls
    assert got["title"] == "T" and got["doing"] == "D", got
    assert got["gist"] == "первый промпт" and got["gistDone"] is True, got


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


def test_an_unexpanded_tilde_still_works_and_leaves_no_stray_dir():
    # CCFZF_FACTS_FILE — значение конфига, не слово шелла: шелл его не
    # разворачивает, и `~/...` доезжает до load_facts/save_facts буквально.
    # write_json разворачивает путь сама (ccfzf:1336), а раньше эти две — нет:
    # save_facts создавала каталог с именем `~` в текущей директории процесса
    # (os.makedirs — путь относительный), write_json тут же падал на
    # несуществующем настоящем каталоге, а load_facts всегда читал бы {}.
    # Памятка при этом выключена молча — никакого исключения наружу.
    with tempfile.TemporaryDirectory() as home, \
            tempfile.TemporaryDirectory() as cwd:
        old_home, old_cwd = os.environ.get("HOME"), os.getcwd()
        os.environ["HOME"] = home
        os.chdir(cwd)
        try:
            facts = {P: {"mtime": 100.0, "title": "T", "doing": "D",
                         "gist": "G", "gistDone": True}}
            CC["save_facts"]("~/.cache/ccfzf/facts.json", facts)
            assert not os.path.exists(os.path.join(cwd, "~")), \
                "не должно быть каталога с буквальным именем ~"
            real = os.path.join(home, ".cache", "ccfzf", "facts.json")
            assert os.path.exists(real), "памятка должна лечь в настоящий HOME"
            got = CC["load_facts"]("~/.cache/ccfzf/facts.json")
            assert got == facts, got
        finally:
            os.chdir(old_cwd)
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home


def test_a_bare_filename_does_not_disable_the_memo():
    # Родственный случай: os.path.dirname("facts.json") — пустая строка, а
    # os.makedirs("") кидает FileNotFoundError. Тот же except OSError её
    # ловил и молча выключал памятку. Каталог создаём, только когда он вообще
    # указан.
    with tempfile.TemporaryDirectory() as cwd:
        old_cwd = os.getcwd()
        os.chdir(cwd)
        try:
            facts = {P: {"mtime": 100.0, "title": "T", "doing": "D",
                         "gist": "G", "gistDone": True}}
            CC["save_facts"]("facts.json", facts)
            assert os.path.exists(os.path.join(cwd, "facts.json"))
            assert CC["load_facts"]("facts.json") == facts
        finally:
            os.chdir(old_cwd)


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
