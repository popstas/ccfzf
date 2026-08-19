"""Достать python-блок из ccfzf и выполнить его в отдельном пространстве имён.

Блок живёт heredoc-ом внутри bash-скрипта, поэтому импортировать его нечем:
файла с ним не существует. Вырезается он по тем же меткам, по которым его
читает сам bash, и выполняется с argv из одного элемента — тогда ни одна
ветка разбора режима не срабатывает и наружу остаются только определения.

Открывающая метка ищется без перевода строки и хвост её строки отбрасывается
отдельно: в скрипте она записана как `read -r -d '' PY <<'PYEOF' || true`, и
поиск по `"<<'PYEOF'\n"` не находит ничего.
"""
import pathlib
import sys

SRC = pathlib.Path(__file__).resolve().parent.parent / "ccfzf"
BEGIN = "<<'PYEOF'"
END = "\nPYEOF"


def load():
    text = SRC.read_text(encoding="utf-8")
    head, marker, rest = text.partition(BEGIN)
    if not marker or END not in rest:
        raise AssertionError("python block markers not found in %s" % SRC)
    body = rest.split("\n", 1)[1].split(END, 1)[0]
    ns = {"__name__": "ccfzf_py"}
    saved = sys.argv
    sys.argv = ["ccfzf"]
    try:
        exec(compile(body, str(SRC), "exec"), ns)
    finally:
        sys.argv = saved
    return ns


def run(argv):
    """Выполнить блок в режиме `argv[0]` и вернуть (stdout, stderr).

    Ветки режимов живут на верхнем уровне блока, импортировать их нечем и
    вызвать по имени тоже: `load()` намеренно запускает блок с пустым argv,
    чтобы ни одна из них не сработала. Здесь наоборот — argv задаётся целиком,
    а оба потока перехватываются, потому что ветка пишет прямо в них.
    """
    import contextlib
    import io

    text = SRC.read_text(encoding="utf-8")
    head, marker, rest = text.partition(BEGIN)
    if not marker or END not in rest:
        raise AssertionError("python block markers not found in %s" % SRC)
    body = rest.split("\n", 1)[1].split(END, 1)[0]
    ns = {"__name__": "ccfzf_py"}
    out, err = io.StringIO(), io.StringIO()
    saved = sys.argv
    sys.argv = ["ccfzf"] + list(argv)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            exec(compile(body, str(SRC), "exec"), ns)
    finally:
        sys.argv = saved
    return out.getvalue(), err.getvalue()
