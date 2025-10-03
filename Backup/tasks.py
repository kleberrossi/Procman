"""tasks.py - utilitário simples de automação local.

Uso rápido:
  python tasks.py run        -> inicia app Flask
  python tasks.py test       -> roda pytest (silencioso)
  python tasks.py test -v    -> roda pytest verboso
  python tasks.py lint       -> (placeholder) ponto para futura checagem
  python tasks.py ci         -> combinação: test (falha se !=0)

Mantido propositalmente enxuto (sem dependência externa tipo invoke/fabric).
"""
from __future__ import annotations
import subprocess, sys, pathlib, os

ROOT = pathlib.Path(__file__).parent
VENV_PY = None  # poderíamos detectar Python do venv aqui futuramente


def _run(cmd: list[str]|str, check=True):
    if isinstance(cmd, str):
        shell=True
    else:
        shell=False
    print(f"[run] {cmd}")
    r = subprocess.run(cmd, shell=shell)
    if check and r.returncode != 0:
        sys.exit(r.returncode)


def task_run(args: list[str]):
    os.environ.setdefault('FLASK_ENV', 'development')
    _run([sys.executable, 'app.py'])


def task_test(args: list[str]):
    extra = args
    cmd = [sys.executable, '-m', 'pytest'] + (extra or ['-q'])
    _run(cmd)


def task_ci(args: list[str]):
    # simples: apenas roda testes (poderia acrescentar lint depois)
    task_test(['-q'])


def task_lint(args: list[str]):
    print("(placeholder) adicionar ferramentas de lint futuramente")


TASKS = {
    'run': task_run,
    'test': task_test,
    'ci': task_ci,
    'lint': task_lint,
}


def main():
    if len(sys.argv) < 2:
        print("Uso: python tasks.py <task> [args...]")
        print("Tasks disponíveis:", ', '.join(TASKS))
        raise SystemExit(1)
    task = sys.argv[1]
    fn = TASKS.get(task)
    if not fn:
        print(f"Task desconhecida: {task}")
        raise SystemExit(2)
    fn(sys.argv[2:])


if __name__ == '__main__':
    main()
