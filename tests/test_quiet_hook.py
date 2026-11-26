"""wt-progress.sh: `turnFrom` (кто начал ход) и `quiet` (тихий конец хода).

turnFrom ставится на start и держится до следующего start; quiet считается на
stop и на idle-уведомлении — по положительным признакам «работа идёт без
человека», без них сессия зовёт, как раньше. Запуск: python3 tests/test_quiet_hook.py
"""
import json
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Home, SID, SUPPORTED, transcript

try:
    import pytest
    pytestmark = pytest.mark.skipif(not SUPPORTED, reason="hooks need Linux with jq in /usr/bin")
except ImportError:
    pytest = None

HEAD = "99999999-2222-4333-8444-555555555555"
OTHER = "88888888-2222-4333-8444-555555555555"
CHILD = "77777777-2222-4333-8444-555555555555"
GRAND = "66666666-2222-4333-8444-555555555555"
# pid отправителя — только ключ к записи в sessions; живость проверяется
# у потомков, и живой у них — сам тест (os.getpid()).
HEAD_PID, OTHER_PID, CHILD_PID, GRAND_PID = 4242, 4343, 4444, 4545
DEAD_PID = 999999999  # больше pid_max: /proc/<pid> нет никогда
FAST = {"QUIET_RECHECK_MS": "300", "QUIET_POLL_MS": "100"}


def peer(pid, body="готово", name="x"):
    return ('<cross-session-message from="uds:/run/user/1000/cc-socks/%d.sock" '
            'from-name="%s" from-mode="prompting">\n%s\n</cross-session-message>' % (pid, name, body))


IDLE_NOTICE = '[Cross-session idle notice] ".child" is idle now.'


class World(Home):
    """HOME с head, сессией SID, её ребёнком CHILD и внуком GRAND."""

    def __init__(self, child_alive=True):
        super().__init__()
        transcript(self.transcript, "q", "Ответ агента")
        self.state_dir.mkdir(parents=True)
        self.sessions = self.home / ".claude" / "sessions"
        self.sessions.mkdir(parents=True)
        self.kids = self.home / ".ccfzf" / "children"
        self.kids.mkdir(parents=True)
        live = os.getpid() if child_alive else DEAD_PID
        self.registry(HEAD_PID, HEAD, HEAD_PID)
        self.registry(OTHER_PID, OTHER, OTHER_PID)
        self.registry(CHILD_PID, CHILD, live)
        self.registry(GRAND_PID, GRAND, live)
        self.child_of(SID, HEAD)
        self.child_of(CHILD, SID)
        self.child_of(GRAND, CHILD)
        # Чужой ребёнок head, не потомок SID: его активность SID не касается.
        self.child_of(OTHER, HEAD)
        self.set_state(OTHER, "active")

    def registry(self, key_pid, sid, pid):
        (self.sessions / ("%d.json" % key_pid)).write_text(json.dumps({"pid": pid, "sessionId": sid}))

    def child_of(self, sid, head):
        (self.kids / (sid + ".json")).write_text(json.dumps({"sessionId": sid, "headId": head}))

    def set_state(self, sid, state):
        p = self.state_dir / (sid + ".state.json")
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"sessionId": sid, "state": state}))
        tmp.replace(p)

    def wait(self, kind):
        (self.state_dir / (SID + ".wait.json")).write_text(
            json.dumps({"sessionId": SID, "kind": kind, "ask": "x", "setAt": 1}))

    def hook(self, event, env=None, **stdin):
        res = self.run("wt-progress.sh", event, stdin=self.stdin(**stdin), env={**FAST, **(env or {})})
        assert res.returncode == 0, res.stderr
        return self.state()

    def start(self, prompt=None, **extra):
        if prompt is not None:
            extra["prompt"] = prompt
        return self.hook("start", hook_event_name="UserPromptSubmit", **extra)

    def stop(self, env=None):
        return self.hook("stop", env=env, hook_event_name="Stop")

    def turn(self, prompt, **extra):
        self.start(prompt, **extra)
        return self.stop()


def origin(prompt, **extra):
    w = World()
    try:
        return w.start(prompt, **extra)["turnFrom"]
    finally:
        w.close()


# ---- turnFrom ----

def test_typed_text_is_human():
    assert origin("сделай X") == "human"
    assert origin("[срочно] сделай X") == "human"
    assert origin("<div> съехал") == "human"


def test_a_message_from_own_head_is_head():
    assert origin(peer(HEAD_PID)) == "head"


def test_a_message_from_a_child_is_child():
    assert origin(peer(CHILD_PID)) == "child"


def test_a_message_from_a_grandchild_is_child():
    assert origin(peer(GRAND_PID)) == "child"


def test_a_message_from_another_session_is_peer():
    assert origin(peer(OTHER_PID)) == "peer"
    assert origin(peer(5555)) == "peer", "неизвестный pid"


def test_harness_notices_are_notice():
    assert origin(IDLE_NOTICE) == "notice"
    assert origin("[Cross-session delivery notice] held") == "notice"
    assert origin("[SYSTEM NOTIFICATION - NOT USER INPUT] done") == "notice"


def test_wrappers_and_empty_prompt_are_wrapper():
    assert origin("<task-notification>\n<task-id>x</task-id>\n</task-notification>") == "wrapper"
    assert origin('<teammate-message teammate_id="a">\nhi\n</teammate-message>') == "wrapper"
    assert origin(None) == "wrapper"
    assert origin("") == "wrapper"


def test_a_prompt_with_agent_id_is_subagent():
    assert origin("сделай X", agent_id="a1") == "subagent"


def test_turn_from_survives_tool_events_and_stop():
    w = World()
    try:
        w.start(peer(CHILD_PID))
        assert w.hook("tool-start", hook_event_name="PreToolUse", tool_name="Bash")["turnFrom"] == "child"
        assert w.hook("tool-done", hook_event_name="PostToolUse", tool_name="Bash")["turnFrom"] == "child"
        assert w.stop()["turnFrom"] == "child"
    finally:
        w.close()


def test_a_start_inside_a_human_turn_does_not_downgrade():
    w = World()
    try:
        w.start("сделай X")
        assert w.start("отчёт", agent_id="a1")["turnFrom"] == "human"
        assert w.start(peer(CHILD_PID))["turnFrom"] == "human"
        assert w.start(peer(HEAD_PID))["turnFrom"] == "head", "head поверх human — можно"
        w.stop()
        assert w.start(IDLE_NOTICE)["turnFrom"] == "notice", "после конца хода — новый ход"
    finally:
        w.close()


# ---- quiet ----

def test_a_child_report_with_the_child_still_active_is_quiet():
    w = World()
    try:
        w.set_state(CHILD, "active")
        s = w.turn(peer(CHILD_PID))
        assert s["state"] == "review" and s["quiet"] is True, s
    finally:
        w.close()


def test_an_active_grandchild_counts():
    w = World()
    try:
        w.set_state(CHILD, "idle")
        w.set_state(GRAND, "active")
        assert w.turn(IDLE_NOTICE)["quiet"] is True
    finally:
        w.close()


def test_a_child_report_with_every_descendant_done_calls():
    w = World()
    try:
        w.set_state(CHILD, "idle")
        w.set_state(GRAND, "review")
        assert w.turn(peer(CHILD_PID))["quiet"] is False
    finally:
        w.close()


def test_a_human_or_head_turn_always_calls():
    w = World()
    try:
        w.set_state(CHILD, "active")
        assert w.turn("сделай X")["quiet"] is False
        assert w.turn(peer(HEAD_PID))["quiet"] is False
    finally:
        w.close()


def test_own_external_wait_is_enough():
    w = World()
    try:
        w.wait("external")
        assert w.turn(IDLE_NOTICE)["quiet"] is True
    finally:
        w.close()


def test_own_decision_or_review_wait_calls_even_with_an_active_child():
    for kind in ("decision", "review"):
        w = World()
        try:
            w.set_state(CHILD, "active")
            w.wait(kind)
            assert w.turn(IDLE_NOTICE)["quiet"] is False, kind
        finally:
            w.close()


def test_a_dead_child_stuck_in_active_does_not_silence():
    w = World(child_alive=False)
    try:
        w.set_state(CHILD, "active")
        assert w.turn(peer(CHILD_PID))["quiet"] is False
    finally:
        w.close()


def test_another_sessions_active_child_does_not_count():
    w = World()
    try:
        w.set_state(CHILD, "idle")  # OTHER (ребёнок HEAD, не SID) — active
        assert w.turn(IDLE_NOTICE)["quiet"] is False
    finally:
        w.close()


def test_a_question_or_failure_calls():
    w = World()
    try:
        w.set_state(CHILD, "active")
        w.start(IDLE_NOTICE)
        s = w.hook("attention", hook_event_name="Notification", message="Claude needs your permission to use Bash")
        assert s["state"] == "question" and s["quiet"] is False
        w.start(IDLE_NOTICE)
        assert w.hook("fail", hook_event_name="StopFailure")["quiet"] is False
    finally:
        w.close()


def test_the_idle_notice_recomputes_and_start_resets():
    w = World()
    try:
        w.set_state(CHILD, "active")
        w.turn(IDLE_NOTICE)
        s = w.hook("attention", hook_event_name="Notification", message="Claude is waiting for your input")
        assert s["state"] == "idle" and s["quiet"] is True, s
        assert w.start("сделай X")["quiet"] is False
    finally:
        w.close()


def test_quiet_survives_a_compaction():
    w = World()
    try:
        w.set_state(CHILD, "active")
        assert w.turn(peer(CHILD_PID))["quiet"] is True
        w.hook("compact", hook_event_name="PreCompact", trigger="auto")
        s = w.hook("compact", hook_event_name="PostCompact", trigger="auto")
        assert s["state"] == "review" and s["quiet"] is True, s
    finally:
        w.close()


def test_race_a_child_that_starts_late_is_still_seen():
    """Head отправил задачу последним шагом хода: start ребёнка позже stop head."""
    w = World()
    try:
        w.set_state(CHILD, "idle")
        w.start(IDLE_NOTICE)
        t = threading.Timer(0.4, w.set_state, (CHILD, "active"))
        t.start()
        try:
            s = w.stop(env={"QUIET_RECHECK_MS": "3000", "QUIET_POLL_MS": "100"})
        finally:
            t.join()
        assert s["quiet"] is True, s
    finally:
        w.close()


def test_race_window_ends_with_a_call():
    w = World()
    try:
        w.set_state(CHILD, "idle")
        w.start(IDLE_NOTICE)
        t0 = time.monotonic()
        s = w.stop(env={"QUIET_RECHECK_MS": "600", "QUIET_POLL_MS": "100"})
        took = time.monotonic() - t0
        assert s["quiet"] is False and took >= 0.5, (s, took)
    finally:
        w.close()


def test_a_human_turn_does_not_wait_for_the_race_window():
    w = World()
    try:
        w.start("сделай X")
        t0 = time.monotonic()
        w.stop(env={"QUIET_RECHECK_MS": "5000"})
        assert time.monotonic() - t0 < 2.5
    finally:
        w.close()


def test_a_child_on_a_question_is_not_work():
    w = World()
    try:
        p = w.state_dir / (CHILD + ".state.json")
        p.write_text(json.dumps({"sessionId": CHILD, "state": "active", "question": "A или B?"}))
        assert w.turn(peer(CHILD_PID))["quiet"] is False
    finally:
        w.close()


def test_no_race_wait_without_live_descendants():
    """Отчёт фонового субагента у сессии без живых детей кончается сразу."""
    for alive in (True, False):
        w = World(child_alive=alive)
        try:
            if alive:  # живых потомков нет: записи children убраны
                for f in w.kids.glob("*.json"):
                    f.unlink()
            else:
                w.set_state(CHILD, "active")  # мёртвый и залипший
            w.start("<task-notification>\n<task-id>x</task-id>\n</task-notification>")
            t0 = time.monotonic()
            s = w.stop(env={"QUIET_RECHECK_MS": "5000"})
            assert s["quiet"] is False and time.monotonic() - t0 < 2.5, alive
        finally:
            w.close()


def test_loud_at_marks_the_last_loud_end_and_survives_quiet_ones():
    w = World()
    try:
        assert w.start("сделай X").get("loudAt", 0) == 0
        loud = w.stop()
        assert loud["quiet"] is False and loud["loudAt"] == loud["updated"], loud
        w.set_state(CHILD, "active")
        time.sleep(1.1)  # новая секунда: тихий конец обязан не сдвинуть loudAt
        q = w.turn(peer(CHILD_PID))
        assert q["quiet"] is True and q["loudAt"] == loud["loudAt"] and q["updated"] > q["loudAt"], q
        idle = w.hook("attention", hook_event_name="Notification", message="Claude is waiting for your input")
        assert idle["quiet"] is True and idle["loudAt"] == loud["loudAt"], idle
        w.hook("compact", hook_event_name="PreCompact", trigger="auto")
        c = w.hook("compact", hook_event_name="PostCompact", trigger="auto")
        assert c["loudAt"] == loud["loudAt"], c
        w.set_state(CHILD, "idle")
        time.sleep(1.1)
        final = w.turn(peer(CHILD_PID))
        assert final["quiet"] is False and final["loudAt"] == final["updated"] > loud["loudAt"], final
    finally:
        w.close()


def test_loud_at_on_failure_and_on_a_loud_idle_notice():
    w = World()
    try:
        w.start(IDLE_NOTICE)
        f = w.hook("fail", hook_event_name="StopFailure")
        assert f["loudAt"] == f["updated"] > 0, f
        w.set_state(f"{SID}", "review")  # сброс файла: без loudAt
        s = w.hook("attention", hook_event_name="Notification", message="Claude is waiting for your input")
        assert s["state"] == "idle" and s["quiet"] is False and s["loudAt"] == s["updated"] > 0, s
    finally:
        w.close()


def test_a_turn_with_a_permission_question_is_never_quiet():
    w = World()
    try:
        w.set_state(CHILD, "active")
        w.start(peer(CHILD_PID))
        q = w.hook("attention", hook_event_name="Notification", message="Claude needs your permission to use Bash")
        assert q["turnAsked"] is True, q
        w.hook("tool-done", hook_event_name="PostToolUse", tool_name="Bash")
        s = w.stop()
        assert s["quiet"] is False and s["loudAt"] == s["updated"] and s["turnAsked"] is True, s
        assert w.start(IDLE_NOTICE)["turnAsked"] is False, "start сбрасывает"
        assert w.stop()["quiet"] is True, "следующий ход без вопроса снова тихий"
    finally:
        w.close()


def test_a_turn_with_ask_user_question_is_never_quiet_even_across_compact():
    w = World()
    try:
        w.wait("external")
        w.start(IDLE_NOTICE)
        w.hook("tool-start", hook_event_name="PreToolUse", tool_name="AskUserQuestion",
               tool_input={"questions": [{"question": "A или B?"}]})
        w.hook("tool-done", hook_event_name="PostToolUse", tool_name="AskUserQuestion")
        w.hook("compact", hook_event_name="PreCompact", trigger="auto")
        c = w.hook("compact", hook_event_name="PostCompact", trigger="auto")
        assert c["turnAsked"] is True, c
        s = w.stop()
        assert s["quiet"] is False and s["loudAt"] == s["updated"], s
    finally:
        w.close()


def test_state_dir_override():
    w = World()
    try:
        alt = w.root / "alt"
        res = w.run("wt-progress.sh", "start", stdin=w.stdin(hook_event_name="UserPromptSubmit", prompt="hi"),
                    env={"CLAUDE_WT_STATE_DIR": str(alt)})
        assert res.returncode == 0, res.stderr
        assert json.loads((alt / (SID + ".state.json")).read_text())["turnFrom"] == "human"
        assert not (w.state_dir / (SID + ".state.json")).exists()
    finally:
        w.close()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
