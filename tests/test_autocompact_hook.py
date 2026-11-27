"""wt-progress.sh: автокомпакт пикера тихий (решение Стаса 27.11, 4a).

`/compact` от `claude-wt session compact` и набранный руками приходят хуку
одинаково: PreCompact/PostCompact с `trigger: manual`, без UserPromptSubmit
(у живых state.json с `event: compact` prompt и turnAt — от прошлого хода).
Различает их строка-намерение session compact в ~/.ccfzf/typed.jsonl.

Ручной — как раньше: review кладётся в idle. Автокомпакт не меняет состояние
просмотра ни в какую сторону, `updated` и `loudAt` прежние, `quiet: true`
(менеджер глушит звонок WezTerm), wait.json не трогается.

Запуск: python3 tests/test_autocompact_hook.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import SID, SUPPORTED
from test_quiet_hook import World

try:
    import pytest
    pytestmark = pytest.mark.skipif(not SUPPORTED, reason="hooks need Linux with jq in /usr/bin")
except ImportError:
    pytest = None

OTHER_SID = "12121212-2222-4333-8444-555555555555"
IDLE = "Claude is waiting for your input"


class CompactWorld(World):
    def journal(self, sid=SID, age=5, **extra):
        """Строка журнала session compact; по умолчанию — намерение Enter."""
        rec = {"at": "2026-11-27T10:00:00.123Z", "command": "compact", "id": sid,
               "text": "/compact", "result": "sending", "step": "enter",
               "atSec": int(time.time()) - age}
        rec.update(extra)
        p = self.home / ".ccfzf" / "typed.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")

    def compact(self):
        self.hook("compact", hook_event_name="PreCompact", trigger="manual")
        return self.hook("compact", hook_event_name="PostCompact", trigger="manual")

    def idle_notice(self):
        return self.hook("attention", hook_event_name="Notification", message=IDLE)

    def raw(self):
        return (self.state_dir / (SID + ".state.json")).read_text(encoding="utf-8")


def finished(w):
    """Ход человека закончен: review, громкий; updated отодвинут в прошлое."""
    s = w.turn("сделай X")
    assert s["state"] == "review" and s["quiet"] is False, s
    p = w.state_dir / (SID + ".state.json")
    o = json.loads(p.read_text(encoding="utf-8"))
    o["updated"] = o["loudAt"] = o["updated"] - 3500
    p.write_text(json.dumps(o))
    return o


def test_manual_compact_still_puts_review_to_idle():
    w = CompactWorld()
    try:
        before = finished(w)
        s = w.compact()
        assert s["state"] == "idle", s
        assert s["updated"] == before["updated"], (s, before)
        assert s["quiet"] is False, s
    finally:
        w.close()


def test_autocompact_keeps_review_and_is_quiet():
    w = CompactWorld()
    try:
        before = finished(w)
        w.journal()
        s = w.compact()
        assert s["state"] == "review", s
        assert s["updated"] == before["updated"], (s, before)
        assert s["loudAt"] == before["loudAt"], (s, before)
        assert s["quiet"] is True, s
        assert s["turnFrom"] == "human" and s["prompt"] == before["prompt"], s
    finally:
        w.close()


def test_autocompact_of_an_idle_session_stays_idle_and_quiet_after_the_notice():
    w = CompactWorld()
    try:
        finished(w)
        before = w.idle_notice()
        assert before["state"] == "idle" and before["quiet"] is False, before
        w.journal()
        s = w.compact()
        assert s["state"] == "idle" and s["quiet"] is True, s
        assert s["updated"] == before["updated"] and s["loudAt"] == before["loudAt"], (s, before)
        # Уведомление о простое поверх idle запись не трогает (как и раньше).
        raw = w.raw()
        w.idle_notice()
        assert w.raw() == raw
    finally:
        w.close()


def test_autocompact_does_not_touch_the_declared_wait():
    w = CompactWorld()
    try:
        finished(w)
        w.wait("external")
        w.journal()
        w.compact()
        assert (w.state_dir / (SID + ".wait.json")).exists()
    finally:
        w.close()


def test_a_stale_foreign_or_unsent_journal_line_is_a_manual_compact():
    for extra in ({"age": 300}, {"sid": OTHER_SID}, {"result": "refused", "step": None},
                  {"step": "text"}, {"command": None}):
        w = CompactWorld()
        try:
            finished(w)
            w.journal(**extra)
            s = w.compact()
            assert s["state"] == "idle", (extra, s)
            assert s["quiet"] is False, (extra, s)
        finally:
            w.close()


def test_a_session_type_line_is_not_an_autocompact():
    # session type пишет childId/text без command — это не автокомпакт, даже
    # если набрали «/compact».
    w = CompactWorld()
    try:
        finished(w)
        p = w.home / ".ccfzf" / "typed.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"at": "2026-11-27T10:00:00.000Z", "childId": SID, "text": "/compact",
                                 "result": "sending", "step": "enter"}) + "\n")
        assert w.compact()["state"] == "idle"
    finally:
        w.close()


def test_the_journal_path_comes_from_the_environment():
    w = CompactWorld()
    try:
        finished(w)
        w.journal()
        moved = w.root / "typed.jsonl"
        (w.home / ".ccfzf" / "typed.jsonl").rename(moved)
        env = {"CLAUDE_WT_TYPED_LOG": str(moved)}
        w.hook("compact", env=env, hook_event_name="PreCompact", trigger="manual")
        s = w.hook("compact", env=env, hook_event_name="PostCompact", trigger="manual")
        assert s["state"] == "review" and s["quiet"] is True, s
    finally:
        w.close()


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
