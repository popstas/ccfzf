"""Хуки состояния сессии из hooks/: синтаксис и запись файлов на фикстуре stdin.

Каждый хук гоняется подпроцессом в подставном HOME и с урезанным PATH
(/usr/bin:/bin): так тест не зависит ни от каталога состояний живой машины, ни
от того, что стоит у неё в ~/bin. Транскрипт — маленький jsonl во временном
каталоге; финальный ответ в нём помечен `end_turn`, иначе stop выстаивал бы
всё ожидание дописи (STOP_WAIT_MS).

Запуск: pytest tests/test_hooks.py
"""
import json
import os
import pathlib
import subprocess
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"
SID = "11111111-2222-4333-8444-555555555555"
PATH = "/usr/bin:/bin"


def transcript(path, prompt, answer, stop_reason="end_turn"):
    """Транскрипт из одного запроса человека и одного ответа агента."""
    rows = [
        {"type": "user", "message": {"role": "user", "content": prompt}},
        {"type": "assistant", "message": {
            "role": "assistant", "stop_reason": stop_reason,
            "content": [{"type": "text", "text": answer}]}},
    ]
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8")


class Home:
    """Временный HOME с каталогом проекта и транскриптом сессии."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.cwd = self.root / "proj"
        self.cwd.mkdir()
        self.transcript = self.root / (SID + ".jsonl")
        self.state_dir = self.home / ".claude" / "claude-wt"

    def close(self):
        self.tmp.cleanup()

    def stdin(self, **extra):
        data = {"session_id": SID, "transcript_path": str(self.transcript),
                "cwd": str(self.cwd)}
        data.update(extra)
        return json.dumps(data, ensure_ascii=False)

    def run(self, script, *args, stdin="", env=None, timeout=10):
        full = {"HOME": str(self.home), "PATH": PATH, "LANG": "C.UTF-8"}
        full.update(env or {})
        return subprocess.run(["bash", str(HOOKS / script)] + list(args),
                              input=stdin, capture_output=True, text=True,
                              env=full, cwd=str(self.cwd), timeout=timeout)

    def state(self):
        return json.loads((self.state_dir / (SID + ".state.json")).read_text(encoding="utf-8"))


def test_hooks_parse():
    """bash -n по каждому хуку: синтаксис не сломан."""
    scripts = sorted(HOOKS.glob("*.sh"))
    assert scripts, "в hooks/ нет ни одного скрипта"
    for script in scripts:
        res = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert res.returncode == 0, "%s: %s" % (script.name, res.stderr)


def test_start_writes_active_state_with_prompt():
    """UserPromptSubmit: active, запрос человека из stdin, отметка начала хода."""
    h = Home()
    try:
        transcript(h.transcript, "старый запрос", "Старый ответ агента целиком")
        res = h.run("wt-progress.sh", "start",
                    stdin=h.stdin(hook_event_name="UserPromptSubmit",
                                  prompt="Почини падающий тест"))
        assert res.returncode == 0, res.stderr
        out = json.loads(res.stdout)
        assert out["suppressOutput"] is True
        assert "\x1b]9;4;1;100" in out["terminalSequence"], "работа — залитый бар"
        st = h.state()
        assert st["state"] == "active"
        assert st["event"] == "start"
        assert st["prompt"] == "Почини падающий тест"
        assert st["turnAt"] > 0
        assert st["summary"] == "", "у работающей сессии текущей сводки нет"
        assert st["cwd"] == str(h.cwd)
    finally:
        h.close()


def test_stop_writes_review_with_summary():
    """Stop: review и сводка — первая содержательная строка ответа."""
    h = Home()
    try:
        transcript(h.transcript, "почини тест",
                   "Готово.\nТест починен, причина была в кодировке\n\nПодробности ниже.")
        t0 = time.time()
        res = h.run("wt-progress.sh", "stop", stdin=h.stdin(hook_event_name="Stop"))
        took = time.time() - t0
        assert res.returncode == 0, res.stderr
        st = h.state()
        assert st["state"] == "review"
        assert st["summary"] == "Готово. Тест починен, причина была в кодировке"
        assert st["lastSummary"] == st["summary"]
        assert st["prompt"] == "почини тест"
        assert took < 1.4, "end_turn в хвосте — ждать дописи незачем (%.2f с)" % took
    finally:
        h.close()


def test_ask_user_question_sets_question():
    """PreToolUse AskUserQuestion кладёт вопрос, PostToolUse той же команды снимает."""
    h = Home()
    try:
        transcript(h.transcript, "спроси", "Сейчас спрошу у человека")
        ask = {"questions": [{"question": "Какую ветку взять?", "header": "Ветка",
                              "options": []}]}
        res = h.run("wt-progress.sh", "tool-start",
                    stdin=h.stdin(hook_event_name="PreToolUse",
                                  tool_name="AskUserQuestion", tool_input=ask))
        assert res.returncode == 0, res.stderr
        assert h.state()["question"] == "Какую ветку взять?"
        res = h.run("wt-progress.sh", "tool-done",
                    stdin=h.stdin(hook_event_name="PostToolUse",
                                  tool_name="AskUserQuestion", tool_input=ask))
        assert res.returncode == 0, res.stderr
        assert h.state()["question"] == ""
    finally:
        h.close()


def test_statusline_numbers_reach_state():
    """Статуслайн кладёт деньги и контекст рядом, wt-progress переносит их в state.json."""
    h = Home()
    try:
        transcript(h.transcript, "q", "Ответ агента подлиннее")
        status_in = h.stdin(cost={"total_cost_usd": 3.6},
                            context_window={"context_window_size": 200000,
                                            "total_input_tokens": 90000,
                                            "total_output_tokens": 10000})
        # --hook: без рендера статуслайна, ccstatusline в урезанном PATH и нет.
        res = h.run("claude-wt-statusline.sh", "--hook", stdin=status_in)
        assert res.returncode == 0, res.stderr
        assert res.stdout == "", "в --hook stdout уходит в контекст модели"
        status = json.loads((h.state_dir / (SID + ".status.json")).read_text())
        assert status["costUsd"] == 4
        assert status["contextPct"] == 50
        res = h.run("wt-progress.sh", "start",
                    stdin=h.stdin(hook_event_name="UserPromptSubmit", prompt="дальше"))
        assert res.returncode == 0, res.stderr
        st = h.state()
        assert st["costUsd"] == 4
        assert st["contextPct"] == 50
    finally:
        h.close()


def test_agent_state_writes_meta():
    """SessionStart: meta.json с id, каталогом, транскриптом и источником."""
    h = Home()
    try:
        res = h.run("claude-wt-agent-state.sh", "session",
                    stdin=h.stdin(hook_event_name="SessionStart", source="startup"))
        assert res.returncode == 0, res.stderr
        assert res.stdout == ""
        meta = json.loads((h.state_dir / (SID + ".meta.json")).read_text())
        assert meta["sessionId"] == SID
        assert meta["cwd"] == str(h.cwd)
        assert meta["transcript"] == str(h.transcript)
        assert meta["source"] == "startup"
        assert meta["started"] > 0
    finally:
        h.close()


def test_agent_state_compact_source():
    """PostCompact без .source пишет source=compact, а не пустую строку."""
    h = Home()
    try:
        res = h.run("claude-wt-agent-state.sh", "session",
                    stdin=h.stdin(hook_event_name="PostCompact", trigger="auto"))
        assert res.returncode == 0, res.stderr
        meta = json.loads((h.state_dir / (SID + ".meta.json")).read_text())
        assert meta["source"] == "compact"
    finally:
        h.close()


# Подставной ccfzf: медленный, чтобы было видно, что хук его не ждёт, и
# пишущий свой argv в файл, чтобы было видно, что он вообще вызван.
FAKE_CCFZF = """#!/bin/sh
sleep "${FAKE_SLEEP:-0}"
printf '%s\\n' "$*" > "$FAKE_OUT"
"""


def fake_clone(root):
    """Клон в миниатюре: hooks/ccfzf-dump.sh и подставной ccfzf рядом."""
    clone = root / "clone"
    (clone / "hooks").mkdir(parents=True)
    (clone / "hooks" / "ccfzf-dump.sh").write_bytes((HOOKS / "ccfzf-dump.sh").read_bytes())
    fake = clone / "ccfzf"
    fake.write_text(FAKE_CCFZF)
    fake.chmod(0o755)
    return clone


def wait_for(path, seconds=5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if path.exists() and path.read_text():
            return path.read_text()
        time.sleep(0.05)
    raise AssertionError("%s так и не появился" % path)


def test_dump_hook_runs_sibling_ccfzf_in_background():
    """Через симлинк в ~/.claude/hooks хук находит ccfzf своего клона и не ждёт его."""
    h = Home()
    try:
        clone = fake_clone(h.root)
        link_dir = h.home / ".claude" / "hooks"
        link_dir.mkdir(parents=True)
        link = link_dir / "ccfzf-dump.sh"
        link.symlink_to(clone / "hooks" / "ccfzf-dump.sh")
        out = h.root / "argv.txt"
        t0 = time.time()
        res = subprocess.run(["bash", str(link)], input=h.stdin(hook_event_name="SessionStart"),
                             capture_output=True, text=True, timeout=10,
                             env={"HOME": str(h.home), "PATH": PATH,
                                  "FAKE_SLEEP": "2", "FAKE_OUT": str(out)})
        took = time.time() - t0
        assert res.returncode == 0, res.stderr
        assert res.stdout == "", "вывод SessionStart уходит в контекст модели"
        assert took < 1.0, "хук ждал ccfzf или держал его пайп (%.2f с)" % took
        assert wait_for(out).strip() == "--dump"
    finally:
        h.close()


def test_dump_hook_env_override():
    """CCFZF_BIN перебивает ccfzf клона."""
    h = Home()
    try:
        fake = h.root / "my-ccfzf"
        fake.write_text(FAKE_CCFZF)
        fake.chmod(0o755)
        out = h.root / "argv.txt"
        res = h.run("ccfzf-dump.sh", stdin=h.stdin(),
                    env={"CCFZF_BIN": str(fake), "FAKE_OUT": str(out)})
        assert res.returncode == 0, res.stderr
        assert wait_for(out).strip() == "--dump"
    finally:
        h.close()


def test_dump_hook_without_ccfzf_is_quiet():
    """ccfzf не нашёлся нигде — хук молча выходит с нулём."""
    h = Home()
    try:
        clone = h.root / "bare" / "hooks"
        clone.mkdir(parents=True)
        script = clone / "ccfzf-dump.sh"
        script.write_bytes((HOOKS / "ccfzf-dump.sh").read_bytes())
        res = subprocess.run(["bash", str(script)], input="{}", capture_output=True,
                             text=True, timeout=10,
                             env={"HOME": str(h.home), "PATH": PATH})
        assert res.returncode == 0
        assert res.stdout == "" and res.stderr == ""
    finally:
        h.close()
