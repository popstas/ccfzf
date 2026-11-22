"""Хуки состояния сессии из hooks/: синтаксис и запись файлов на фикстуре stdin.

Каждый хук гоняется подпроцессом в подставном HOME и с урезанным PATH
(/usr/bin:/bin): так тест не зависит ни от каталога состояний живой машины, ни
от того, что стоит у неё в ~/bin. Транскрипт — маленький jsonl во временном
каталоге; финальный ответ в нём помечен `end_turn`, иначе stop выстаивал бы
всё ожидание дописи (STOP_WAIT_MS).

Запуск: python3 tests/test_hooks.py
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

try:
    import pytest
except ImportError:
    pytest = None

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


# Хуки — линуксовые: jq, GNU stat -c, /proc. Вне Linux или без jq их прогон
# не про этот репозиторий, а про машину.
SUPPORTED = sys.platform == "linux" and os.path.exists("/usr/bin/jq")
if pytest is not None:
    pytestmark = pytest.mark.skipif(not SUPPORTED, reason="hooks need Linux with jq in /usr/bin")


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
        # Режим statusLine: вход уходит подставному ccstatusline, его вывод — наружу.
        stub = h.root / "bin"
        stub.mkdir()
        (stub / "ccstatusline").write_text("#!/bin/sh\ncat >/dev/null\necho STATUS-LINE\n")
        (stub / "ccstatusline").chmod(0o755)
        res = h.run("claude-wt-statusline.sh", stdin=status_in,
                    env={"PATH": "%s:%s" % (stub, PATH)})
        assert res.returncode == 0, res.stderr
        assert res.stdout.strip() == "STATUS-LINE"
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


# --- установщик ------------------------------------------------------------

HOOK_FILES = ["wt-progress.sh", "claude-wt-statusline.sh",
              "claude-wt-agent-state.sh", "ccfzf-dump.sh"]


def plain_clone(root):
    """Копия клона без git: так ставят из архива, и проверки worktree там нет."""
    clone = root / "clone"
    (clone / "hooks").mkdir(parents=True)
    for f in HOOK_FILES + ["install.sh"]:
        (clone / "hooks" / f).write_bytes((HOOKS / f).read_bytes())
    return clone


def install(h, clone, *args):
    return subprocess.run(["bash", str(clone / "hooks" / "install.sh")] + list(args),
                          capture_output=True, text=True, timeout=20,
                          env={"HOME": str(h.home), "PATH": PATH, "LANG": "C.UTF-8"})


def test_install_links_every_hook():
    """Пустой ~/.claude: симлинк на каждый хук клона и фрагмент настроек в stdout."""
    h = Home()
    try:
        clone = plain_clone(h.root)
        res = install(h, clone)
        assert res.returncode == 0, res.stderr
        for f in HOOK_FILES:
            link = h.home / ".claude" / "hooks" / f
            assert link.is_symlink(), f
            assert os.path.realpath(link) == str((clone / "hooks" / f).resolve())
        start = res.stdout.index("{")
        fragment = json.loads(res.stdout[start:res.stdout.rindex("}") + 1])
        commands = json.dumps(fragment)
        for f in HOOK_FILES:
            assert f in commands, "%s нет во фрагменте настроек" % f
        assert fragment["statusLine"]["command"] == "bash ~/.claude/hooks/claude-wt-statusline.sh"
        dump = [c["command"] for g in fragment["hooks"]["SessionStart"] for c in g["hooks"]]
        assert "bash ~/.claude/hooks/ccfzf-dump.sh" in dump
        assert not (h.home / ".claude" / "settings.json").exists(), "settings.json не трогаем"
    finally:
        h.close()


def test_install_is_idempotent_and_keeps_settings():
    """Повторный запуск ничего не меняет и бэкапов не плодит; settings.json цел."""
    h = Home()
    try:
        clone = plain_clone(h.root)
        settings = h.home / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text('{"model": "x"}\n')
        assert install(h, clone).returncode == 0
        res = install(h, clone)
        assert res.returncode == 0, res.stderr
        hooks_dir = h.home / ".claude" / "hooks"
        assert sorted(p.name for p in hooks_dir.iterdir()) == sorted(HOOK_FILES)
        assert settings.read_text() == '{"model": "x"}\n'
    finally:
        h.close()


def test_install_backs_up_a_different_file():
    """Свой файл на месте хука уходит в .bak-<дата>, одинаковый — заменяется молча."""
    h = Home()
    try:
        clone = plain_clone(h.root)
        hooks_dir = h.home / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "wt-progress.sh").write_text("# старая версия\n")
        (hooks_dir / "ccfzf-dump.sh").write_bytes((HOOKS / "ccfzf-dump.sh").read_bytes())
        res = install(h, clone)
        assert res.returncode == 0, res.stderr
        day = time.strftime("%Y-%m-%d")
        bak = hooks_dir / ("wt-progress.sh.bak-" + day)
        assert bak.read_text() == "# старая версия\n"
        assert (hooks_dir / "wt-progress.sh").is_symlink()
        assert (hooks_dir / "ccfzf-dump.sh").is_symlink()
        assert not list(hooks_dir.glob("ccfzf-dump.sh.bak*")), "одинаковый файл без бэкапа"
        # Второй чужой файл в тот же день не затирает первый бэкап.
        (hooks_dir / "wt-progress.sh").unlink()
        (hooks_dir / "wt-progress.sh").write_text("# ещё одна версия\n")
        assert install(h, clone).returncode == 0
        assert bak.read_text() == "# старая версия\n"
        baks = sorted(p.read_text() for p in hooks_dir.glob("wt-progress.sh.bak-*"))
        assert baks == ["# ещё одна версия\n", "# старая версия\n"]
    finally:
        h.close()


def test_install_dry_run_changes_nothing():
    """--dry-run говорит, что сделал бы, и ничего не создаёт."""
    h = Home()
    try:
        clone = plain_clone(h.root)
        res = install(h, clone, "--dry-run")
        assert res.returncode == 0, res.stderr
        assert "wt-progress.sh" in res.stdout
        assert not (h.home / ".claude").exists()
    finally:
        h.close()


def test_install_refuses_from_a_worktree():
    """Из git worktree не ставит: симлинки смотрели бы в каталог, который удалят."""
    h = Home()
    try:
        main = h.root / "main"
        main.mkdir()
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
        env = {"HOME": str(h.home), "PATH": PATH}
        subprocess.run(git + ["init", "-q", str(main)], check=True, env=env)
        (main / "hooks").mkdir()
        for f in HOOK_FILES + ["install.sh"]:
            (main / "hooks" / f).write_bytes((HOOKS / f).read_bytes())
        subprocess.run(git + ["-C", str(main), "add", "."], check=True, env=env)
        subprocess.run(git + ["-C", str(main), "commit", "-qm", "init"], check=True, env=env)
        wt = h.root / "wt"
        subprocess.run(git + ["-C", str(main), "worktree", "add", "-q", str(wt)],
                       check=True, env=env)
        res = install(h, wt)
        assert res.returncode != 0
        assert "worktree" in res.stderr
        assert str(main) in res.stderr, "в отказе назван основной клон"
        assert not (h.home / ".claude" / "hooks").exists()
        assert install(h, main).returncode == 0, "из основного клона ставит"
    finally:
        h.close()


def test_docs_fragment_matches_installer():
    """Фрагмент settings.json в docs/hooks.md — тот же, что печатает установщик."""
    h = Home()
    try:
        res = install(h, plain_clone(h.root), "--dry-run")
        printed = json.loads(res.stdout[res.stdout.index("{"):res.stdout.rindex("}") + 1])
        doc = (ROOT / "docs" / "hooks.md").read_text(encoding="utf-8")
        block = doc.split("```json\n", 1)[1].split("```", 1)[0]
        assert json.loads(block) == printed
    finally:
        h.close()


if __name__ == "__main__":
    if not SUPPORTED:
        print("skip: hooks need Linux with jq in /usr/bin")
        sys.exit(0)
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
