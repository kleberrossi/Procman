import pathlib, re

# Guardrails para evitar reintrodução de padrões banidos em código ativo.
# Diretórios ignorados deliberadamente: Backup, Mockup, static/css/Backup etc.
# Regras:
#  - Não pode aparecer classes sufixadas -v2 nas listas principais
#  - Não pode voltar status-badge / status-pill
#  - Não pode aparecer wrapper cwb-v2
#  - Caso surja, o teste falha orientando correção

BANNED_PATTERNS = [
    r"cwb-v2",
    r"status-badge",
    r"status-pill",
    r"[A-Za-z0-9_-]+-v2"  # genérico: qualquer classe/identificador terminando em -v2
]

# Diretórios raiz a inspecionar
ROOT = pathlib.Path(__file__).resolve().parents[1]  # src/

IGNORE_DIR_NAMES = {"Backup", "Mockup", "__pycache__"}
IGNORE_FILE_EXT = {"png", "jpg", "jpeg", "gif", "svg", "woff2", "woff"}

# Limita a escanear tipos de texto comuns
INCLUDE_FILE_EXT = {"py", "html", "js", "css"}


def iter_files():
    for path in ROOT.rglob('*'):
        if path.is_dir():
            if path.name in IGNORE_DIR_NAMES:
                # pular subárvore inteira
                dirs = list(path.iterdir())  # force listing to ensure we don't descend
                continue
            continue
        if path.suffix.lstrip('.') not in INCLUDE_FILE_EXT:
            continue
        # pular se algum ancestral é ignorado
        if any(p.name in IGNORE_DIR_NAMES for p in path.parents):
            continue
        yield path


def test_no_banned_patterns():
    violations = []
    compiled = [re.compile(p) for p in BANNED_PATTERNS]
    for file_path in iter_files():
        try:
            text = file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:  # pragma: no cover
            continue
        for regex in compiled:
            for m in regex.finditer(text):
                # Permitir ocorrências em comentários que documentam política? Mantemos bloqueio total para força.
                violations.append(f"{file_path.relative_to(ROOT)}:{m.start()} -> '{m.group(0)}'")
    # Filtra falso positivo: permitir --btn-focus-ring alias de tokens (não tem -v2)
    # (sem filtros adicionais por ora)
    assert not violations, (
        "Padrões banidos encontrados (evitar reintrodução de legado). Revise e remova:\n" +
        "\n".join(violations)
    )
