"""wt-progress.sh start снимает объявленное ожидание (`<id>.wait.json`).

Снимает промпт человека и сообщение своего head; отчёт субагента, сообщение
чужой сессии и пустой prompt — нет. Запуск: python3 tests/test_wait_hook.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hooks import Home, SID, SUPPORTED, transcript

try:
    import pytest
    pytestmark = pytest.mark.skipif(not SUPPORTED, reason="hooks need Linux with jq in /usr/bin")
except ImportError:
    pytest = None

HEAD = "99999999-2222-4333-8444-555555555555"
OTHER = "88888888-2222-4333-8444-555555555555"
HEAD_PID, OTHER_PID = 4242, 4343


def peer(pid, body="готово, мержу", name="co-x"):
    return ('<cross-session-message from="uds:/run/user/1000/cc-socks/%d.sock" '
            'from-name="%s" from-mode="prompting">\n%s\n</cross-session-message>' % (pid, name, body))


def run_start(prompt, children=True, **stdin_extra):
    h = Home()
    try:
        transcript(h.transcript, "q", "Жду твоего решения")
        h.state_dir.mkdir(parents=True)
        wait = h.state_dir / (SID + ".wait.json")
        wait.write_text(json.dumps({"sessionId": SID, "kind": "decision", "ask": "A или B?", "setAt": 1}))
        sessions = h.home / ".claude" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / ("%d.json" % HEAD_PID)).write_text(json.dumps({"pid": HEAD_PID, "sessionId": HEAD}))
        (sessions / ("%d.json" % OTHER_PID)).write_text(json.dumps({"pid": OTHER_PID, "sessionId": OTHER}))
        if children:
            kids = h.home / ".ccfzf" / "children"
            kids.mkdir(parents=True)
            (kids / (SID + ".json")).write_text(json.dumps({"sessionId": SID, "headId": HEAD}))
        extra = {"hook_event_name": "UserPromptSubmit", **stdin_extra}
        if prompt is not None:
            extra["prompt"] = prompt
        res = h.run("wt-progress.sh", "start", stdin=h.stdin(**extra))
        assert res.returncode == 0, res.stderr
        assert h.state()["state"] == "active"
        return wait.exists()
    finally:
        h.close()


def test_a_human_prompt_clears_the_wait():
    assert run_start("Берём B") is False


def test_a_message_from_own_head_clears_the_wait():
    assert run_start(peer(HEAD_PID)) is False


def test_a_message_from_another_session_keeps_the_wait():
    assert run_start(peer(OTHER_PID)) is True


def test_a_head_message_without_a_children_record_keeps_the_wait():
    assert run_start(peer(HEAD_PID), children=False) is True


def test_a_message_from_an_unknown_pid_keeps_the_wait():
    assert run_start(peer(5555)) is True


def test_a_subagent_report_keeps_the_wait():
    assert run_start("<task-notification>\n<task-id>x</task-id>\n</task-notification>") is True


def test_another_harness_wrapper_keeps_the_wait():
    assert run_start('<teammate-message teammate_id="a">\nhi\n</teammate-message>') is True


def test_an_empty_prompt_keeps_the_wait():
    assert run_start(None) is True
    assert run_start("") is True


def test_a_subagent_prompt_keeps_the_wait():
    assert run_start("сделай X", agent_id="a1b2c3") is True


def test_a_cross_session_idle_notice_keeps_the_wait():
    assert run_start('[Cross-session idle notice] ".child", which you asked to be notified about, '
                     'is idle now \u2014 it finished a turn at 23:21. This is a notice from the harness.') is True


def test_a_cross_session_delivery_notice_keeps_the_wait():
    assert run_start('[Cross-session delivery notice] Your message to ".child" was held for its user.') is True


def test_any_other_cross_session_notice_keeps_the_wait():
    assert run_start('[Cross-session something new] text') is True


def test_a_system_notification_frame_keeps_the_wait():
    assert run_start('[SYSTEM NOTIFICATION - NOT USER INPUT] task finished') is True


def test_human_text_that_starts_with_a_bracket_still_clears():
    assert run_start("[срочно] берём B") is False
    assert run_start("[Cross-session] это я пишу руками") is False, "без пробела после session — не заголовок харнесса"


def test_human_text_that_starts_with_a_tag_still_clears():
    assert run_start("<div> съехал, поправь") is False


def test_start_without_a_wait_file_is_fine():
    h = Home()
    try:
        transcript(h.transcript, "q", "a")
        res = h.run("wt-progress.sh", "start", stdin=h.stdin(hook_event_name="UserPromptSubmit", prompt="hi"))
        assert res.returncode == 0, res.stderr
        assert not (h.state_dir / (SID + ".wait.json")).exists()
    finally:
        h.close()


def test_tool_events_do_not_clear():
    h = Home()
    try:
        transcript(h.transcript, "q", "a")
        h.state_dir.mkdir(parents=True)
        wait = h.state_dir / (SID + ".wait.json")
        wait.write_text("{}")
        res = h.run("wt-progress.sh", "tool-start", stdin=h.stdin(hook_event_name="PreToolUse", tool_name="Bash", prompt="x"))
        assert res.returncode == 0, res.stderr
        assert wait.exists()
    finally:
        h.close()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
