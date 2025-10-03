# -*- coding: utf-8 -*-
"""Aplicação Flask principal.

TOC (somente comentários, nenhuma mudança funcional):
    1. Imports & App init
    2. Config & Helpers utilitários
    3. Compat helpers (alias de colunas / safe_insert / safe_update)
    4. NCM heurística
    5. Rotas: Init / Health / Index
    6. REST: Clientes
    7. REST: NCM (fiscal)
    8. REST: Embalagens Master
    9. REST: Pedidos & Itens
 10. REST: Cálculos
 11. REST: Impressão
 12. REST: Gate (elegibilidade)
 13. REST: Produção (Corte & Solda)
 14. REST: Qualidade (QC genérico)
 15. REST: Expedição
 16. REST: Colaboradores
 17. REST/Páginas: Login / Sessão
 18. Páginas (HTML views) clientes / embalagens / pedidos ... colaboradores etc.
 19. REST/Páginas: Parceiros
 20. Rotas util (__routes__, __dbdiag__)
 21. Main guard

Manter a ordem evita efeitos colaterais de dependências implícitas.
"""
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
import re
from functools import wraps
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from db import get_conn, init_db, DB_PATH, bootstrap_db, gerar_codigo_pedido
from calc import massa_por_unidade, unidades_estimadas_por_peso, unidades_minimas


app = Flask(__name__)
# Cria/atualiza o banco automaticamente na subida (idempotente)
bootstrap_db()

# ===== Config =====
app.secret_key = os.environ.get("APP_SECRET_KEY", "mude-esta-chave")

# ==========================
# Helpers
# ==========================
def login_required(view_fn):
    @wraps(view_fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return view_fn(*args, **kwargs)
    return wrapper

def only_digits(s: str) -> str:
    return re.sub(r"\D+", "", s or "")

# ===== Cliente: geração de código sequencial =====
_CLIENT_CODE_REGEX = re.compile(r"^C(\d{5})$")
_PARTNER_CODE_REGEX = re.compile(r"^P(\d{5})$")

def generate_next_client_code(conn: sqlite3.Connection) -> str:
    """Gera próximo código C00000..C99999 baseado no maior existente válido.
    Não faz reserva; deve ser chamado dentro da mesma transação do INSERT.
    """
    cur = conn.execute("SELECT codigo_interno FROM clientes WHERE codigo_interno LIKE 'C_____'")
    max_seq = -1
    for (code,) in cur.fetchall():
        if not code:
            continue
        m = _CLIENT_CODE_REGEX.match(code.strip())
        if m:
            n = int(m.group(1))
            if n > max_seq:
                max_seq = n
    nxt = max_seq + 1
    if nxt > 99999:
        # Limite atingido – gera fallback simples (sem quebrar app)
        return "C99999"
    return f"C{nxt:05d}"

def generate_next_partner_code(conn: sqlite3.Connection) -> str:
    """Gera próximo código P00000..P99999 baseado no maior existente válido.
    Não reserva gaps; deve ser chamado na mesma transação do INSERT.
    """
    cur = conn.execute("SELECT codigo_interno FROM parceiros WHERE codigo_interno LIKE 'P_____'")
    max_seq = -1
    for (code,) in cur.fetchall():
        if not code:
            continue
        m = _PARTNER_CODE_REGEX.match(code.strip())
        if m:
            n = int(m.group(1))
            if n > max_seq:
                max_seq = n
    nxt = max_seq + 1
    if nxt > 99999:
        return "P99999"
    return f"P{nxt:05d}"

def preview_next_client_code() -> str:
    """Apenas para exibir no formulário de NOVO cliente antes de salvar.
    Se houver falha, retorna placeholder."""
    try:
        with get_conn() as conn:
            return generate_next_client_code(conn)
    except Exception:
        return "C-----"

def current_user_is_admin() -> bool:
    return (session.get("user_id") is not None) and (session.get("user_email") is not None) and session.get("user_papel") == 'admin'

def bad_request(msg: str, extra: dict | None = None):
    payload = {"error": msg}
    if extra:
        payload.update(extra)
    return jsonify(payload), 400

# ==========================
# Pedido helpers (totais)
# ==========================
def _recalc_pedido_totais(conn: sqlite3.Connection, pedido_id: int) -> float | None:
    """Recalcula preço_total do pedido.

    Regra:
      - Se existirem itens: soma(qtd * preco_unit) ignorando nulos.
      - Se NÃO existirem itens: tenta fallback preco_base * quantidade_planejada se ambos presentes.
      - Atualiza campo preco_total e retorna novo valor (ou None se não calculado).
    """
    ped = conn.execute("SELECT id, preco_base, quantidade_planejada FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
    if not ped:
        return None
    itens = conn.execute("SELECT preco_unit, qtd FROM pedido_itens WHERE pedido_id=?", (pedido_id,)).fetchall()
    new_total: float | None = None
    if itens:
        total = 0.0
        for pu, qtd in itens:
            try:
                total += float(pu or 0) * float(qtd or 0)
            except Exception:
                pass
        new_total = total
    else:
        try:
            if ped["preco_base"] is not None and ped["quantidade_planejada"] is not None:
                new_total = float(ped["preco_base"]) * float(ped["quantidade_planejada"])
        except Exception:
            new_total = ped["preco_base"]  # fallback mínimo
    conn.execute("UPDATE pedidos SET preco_total=? WHERE id=?", (new_total, pedido_id))
    return new_total

def current_user_role() -> str:
    return session.get("user_papel") or "leitura"

def require_roles(*roles):
    def decorator(fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            if current_user_role() not in roles and not current_user_is_admin():
                return jsonify({"error": "permissão negada"}), 403
            return fn(*args, **kwargs)
        return inner
    return decorator

# Monta string combinada de contato (nome / email / telefone)
def _compose_contato(row_like: Dict[str, Any]) -> str:
    nome = (row_like.get("contato_nome") or "").strip()
    email = (row_like.get("contato_email") or "").strip()
    fone = (row_like.get("contato_telefone") or "").strip()
    parts = [p for p in [nome, email, fone] if p]
    return " / ".join(parts)

# ==========================
# Compat de schema (helpers)
# ==========================
def get_table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]  # nome da coluna é índice 1

# mapeia chaves lógicas -> preferências de colunas reais (na ordem)
_COL_ALIAS_PREFS: Dict[str, Tuple[str, ...]] = {
    "endereco": ("endereco", "rua"),
    "estado":   ("estado", "uf"),
    # contato fracionado
    "contato_nome": ("contato_nome",),
    "contato_email": ("contato_email",),
    "contato_telefone": ("contato_telefone",),
}

def pick_col(cols: List[str], logical_key: str) -> Optional[str]:
    prefs = _COL_ALIAS_PREFS.get(logical_key)
    if prefs:
        for name in prefs:
            if name in cols:
                return name
    return logical_key if logical_key in cols else None

def safe_insert(conn: sqlite3.Connection, table: str, logical_data: Dict[str, Any]) -> int:
    """
    Monta INSERT só com colunas que existem e aplica aliases (ex.: estado->uf).
    Se existir apenas 'contato' (campo único), e não existirem contato_nome/email/telefone,
    condensamos os 3 num texto e gravamos em 'contato'.
    """
    cols = get_table_columns(conn, table)
    real_cols: List[str] = []
    values: List[Any] = []

    # contato "único"
    has_contato_unico = "contato" in cols and not any(
        c in cols for c in ("contato_nome", "contato_email", "contato_telefone")
    )

    for logical_key, v in logical_data.items():
        real = pick_col(cols, logical_key)
        if real:
            real_cols.append(real)
            values.append(v)

    if has_contato_unico:
        nome = str(logical_data.get("contato_nome") or "").strip()
        email = str(logical_data.get("contato_email") or "").strip()
        fone = str(logical_data.get("contato_telefone") or "").strip()
        bloco = " / ".join([p for p in [nome, email, fone] if p])
        if bloco:
            real_cols.append("contato")
            values.append(bloco)

    if not real_cols:
        raise ValueError(f"Sem colunas válidas para inserir em {table}")

    sql = f"INSERT INTO {table} ({', '.join(real_cols)}) VALUES ({', '.join(['?']*len(real_cols))})"
    cur = conn.execute(sql, tuple(values))
    return cur.lastrowid

def safe_update(conn: sqlite3.Connection, table: str, row_id: int, logical_data: Dict[str, Any]) -> None:
    """
    UPDATE defensivo como o safe_insert: só atualiza colunas existentes
    (aplicando aliases). Também trata 'contato' único.
    """
    cols = get_table_columns(conn, table)
    sets: List[str] = []
    values: List[Any] = []

    # contato "único"
    has_contato_unico = "contato" in cols and not any(
        c in cols for c in ("contato_nome", "contato_email", "contato_telefone")
    )

    for logical_key, v in logical_data.items():
        real = pick_col(cols, logical_key)
        if real:
            sets.append(f"{real}=?")
            values.append(v)

    if has_contato_unico:
        nome = str(logical_data.get("contato_nome") or "").strip()
        email = str(logical_data.get("contato_email") or "").strip()
        fone = str(logical_data.get("contato_telefone") or "").strip()
        bloco = " / ".join([p for p in [nome, email, fone] if p])
        if bloco and "contato" in cols and "contato=?" not in sets:
            sets.append("contato=?")
            values.append(bloco)

    if not sets:
        return
    values.append(row_id)
    sql = f"UPDATE {table} SET {', '.join(sets)} WHERE id=?"
    conn.execute(sql, tuple(values))

# ==========================
# NCM — sugestão opcional (heurística simples)
# ==========================
from typing import Optional  # já está importado no topo; mantenha

def _suggest_ncm_by_material_form(material: Optional[str], forma: Optional[str] = None) -> Optional[str]:
    """
    Heurística leve e NÃO vinculante para sugerir NCM.
    Ajuste/expanda conforme seu catálogo.
    """
    m = (material or "").lower()
    f = (forma or "").lower()
    # Exemplo: sacola de polietileno → 39232110
    if "poliet" in m and f == "sacola":
        return "39232110"
    return None

# ==========================
# NCM helpers básicos (normalização/validação)
# ==========================
_NCM_CODE_RE = re.compile(r"^\d{8}$")

def normalize_ncm(raw: Optional[str]) -> Optional[str]:
    """Remove caracteres não numéricos e retorna código de 8 dígitos ou None.
    Aceita entradas como '3923.21.10' e devolve '39232110'."""
    if not raw:
        return None
    digits = re.sub(r"\D+", "", raw)
    if len(digits) != 8:
        return None
    return digits

def validate_ncm_or_none(conn: sqlite3.Connection, ncm: Optional[str]) -> tuple[bool, str]:
    """Valida NCM se fornecido. Se None, considera válido.
    Futuramente pode consultar tabela ncm se existir."""
    if ncm is None:
        return True, ""
    if not _NCM_CODE_RE.match(ncm):
        return False, "NCM deve ter 8 dígitos."
    # Checagem opcional de existência da tabela e do código
    if 'ncm' in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
        # tabela existe – tentar lookup
        cur = conn.execute("SELECT 1 FROM ncm WHERE codigo=? LIMIT 1", (ncm,))
        if not cur.fetchone():
            return False, "NCM inexistente"
    return True, ""

# Stubs utilitários NCM utilizados nas rotas; se desejar, substituir por implementação completa.
def ncm_table_ready(conn: sqlite3.Connection) -> bool:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ncm'")
    return cur.fetchone() is not None

def get_ncm_info(conn: sqlite3.Connection, codigo: str) -> Optional[dict]:
    if not ncm_table_ready(conn):
        return None
    row = conn.execute("SELECT codigo, descricao FROM ncm WHERE codigo=?", (codigo,)).fetchone()
    if not row:
        return None
    return {"codigo": row["codigo"], "descricao": row["descricao"]}



# ==========================
# INIT / HEALTH
# ==========================
@app.route("/init-db", methods=["POST"])
def route_init_db():
    init_db()
    return jsonify({"ok": True})

@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard_page"))
    return redirect(url_for("login"))

# ==========================
# CLIENTES (REST)
# ==========================
@app.route("/api/clientes", methods=["GET"])
def api_clientes_list():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM clientes ORDER BY id DESC").fetchall()
        return jsonify([dict(r) for r in rows])

@app.route("/api/clientes", methods=["POST"])
def api_clientes_create():
    data = request.json or {}

    # Normalizações/validações básicas
    razao_social = (data.get("razao_social") or "").strip()
    cnpj = only_digits(data.get("cnpj") or "")
    cep = only_digits(data.get("cep") or "")
    estado = (data.get("estado") or "").strip().upper()[:2]
    cidade = (data.get("cidade") or "").strip()
    pais = (data.get("pais") or "Brasil").strip()

    if not razao_social or not cnpj:
        return bad_request("Preencha Razão social e CNPJ.")
    if len(cnpj) != 14:
        return bad_request("CNPJ inválido (precisa ter 14 dígitos).")
    if cep and len(cep) != 8:
        return bad_request("CEP deve ter 8 dígitos (somente números).")
    if estado and len(estado) != 2:
        return bad_request("Estado (UF) deve ter 2 letras.")

    with get_conn() as conn:
        ex = conn.execute("SELECT id FROM clientes WHERE cnpj=?", (cnpj,)).fetchone()
        if ex:
            return bad_request("CNPJ já cadastrado.", {"cliente_id": ex["id"]})

        payload = {
            "razao_social": razao_social,
            "cnpj": cnpj,
            "endereco": (data.get("endereco") or "").strip(),
            "bairro": (data.get("bairro") or "").strip(),
            "complemento": (data.get("complemento") or "").strip(),
            "cep": cep,
            "estado": estado,
            "cidade": cidade,
            "pais": pais,
            "codigo_interno": (data.get("codigo_interno") or "").strip(),
            "contato_nome": (data.get("contato_nome") or "").strip(),
            "contato_email": (data.get("contato_email") or "").strip(),
            "contato_telefone": (data.get("contato_telefone") or "").strip(),
            "representante": (data.get("representante") or "").strip(),
            "comissao_percent": float(data.get("comissao_percent") or 0),
            "ncm_padrao": (data.get("ncm_padrao") or "").strip(),
            "observacoes": (data.get("observacoes") or "").strip(),
        }
        # Se não veio código interno, gerar sequencial (evita colisão de UNIQUE em branco)
        if not payload["codigo_interno"]:
            try:
                payload["codigo_interno"] = generate_next_client_code(conn)
            except Exception:
                # fallback seguro (não quebra request; deixa vazio se algo falhar)
                payload["codigo_interno"] = None
        cid = safe_insert(conn, "clientes", payload)
        row = conn.execute("SELECT * FROM clientes WHERE id=?", (cid,)).fetchone()
        return jsonify(dict(row)), 201

# ---- DELETE cliente
@app.route("/api/clientes/<int:id>", methods=["DELETE"])
@login_required
def api_clientes_delete(id: int):
    try:
        with get_conn() as conn:
            ex = conn.execute("SELECT id FROM clientes WHERE id=?", (id,)).fetchone()
            if not ex:
                return jsonify({"error": "cliente não encontrado"}), 404
            conn.execute("DELETE FROM clientes WHERE id=?", (id,))
            conn.commit()
        return ("", 204)
    except sqlite3.IntegrityError:
        return jsonify({"error": "Não é possível deletar: há registros vinculados."}), 409

# ==========================
# FISCAL — NCM (API para autocomplete/validação)
# ==========================
@app.get("/api/ncm")
def api_ncm_search():
    term = (request.args.get("q") or "").strip()
    if not term:
        return jsonify([])
    with get_conn() as conn:
        if not ncm_table_ready(conn):
            # Sem tabela -> não falha, só retorna vazio
            return jsonify([])
        # Busca por código (prefixo) OU descrição
        rows: List[sqlite3.Row]
        if term.isdigit():
            q = term + "%"
            rows = conn.execute(
                "SELECT codigo, descricao FROM ncm WHERE codigo LIKE ? ORDER BY codigo LIMIT 20",
                (q,),
            ).fetchall()
        else:
            q = f"%{term}%"
            rows = conn.execute(
                "SELECT codigo, descricao FROM ncm WHERE descricao LIKE ? ORDER BY descricao LIMIT 20",
                (q,),
            ).fetchall()
        return jsonify([{"codigo": r["codigo"], "descricao": r["descricao"]} for r in rows])

@app.get("/api/ncm/<codigo>")
def api_ncm_get(codigo: str):
    cod = normalize_ncm(codigo)
    if not cod:
        return jsonify({"ok": False, "msg": "NCM deve ter 8 dígitos."}), 400
    with get_conn() as conn:
        info = get_ncm_info(conn, cod)
        if not info:
            # Se tabela não existe ou código não encontrado
            if not ncm_table_ready(conn):
                return jsonify({"ok": False, "msg": "Tabela NCM não instalada."}), 503
            return jsonify({"ok": False, "msg": "NCM inexistente"}), 404
        info["ok"] = True
        return jsonify(info)


# ==========================
# EMBALAGEM MASTER (REST)
# ==========================
@app.route("/api/embalagens", methods=["GET"])
def api_embalagens_list():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT em.*, c.razao_social AS cliente_nome
            FROM embalagem_master em
            LEFT JOIN clientes c ON c.id = em.cliente_id
            ORDER BY em.id DESC
        """).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route("/api/embalagens", methods=["POST"])
def api_embalagens_create():
    data = request.json or {}

    # normalizações comuns
    def to_int(x):
        try:
            return int(float(str(x).replace(",", ".").strip()))
        except Exception:
            return None

    payload = {
        "embalagem_code": (data.get("embalagem_code") or "").strip(),
        "rev": (data.get("rev") or "R00").strip() or None,
        "cliente_id": data.get("cliente_id"),
        "material": (data.get("material") or "").strip(),
        "espessura_um": to_int(data.get("espessura_um")),
        "largura_mm": to_int(data.get("largura_mm")),
        "altura_mm": to_int(data.get("altura_mm")),
        "sanfona_mm": to_int(data.get("sanfona_mm")) or 0,
        "aba_mm": to_int(data.get("aba_mm")) or 0,
        "fita_tipo": (data.get("fita_tipo") or "nenhuma").strip(),
        "impresso": 1 if data.get("impresso") else 0,
        "layout_png": (data.get("layout_png") or "").strip() or None,
        "transparencia": to_int(data.get("transparencia")),
        "resistencia_mecanica": (data.get("resistencia_mecanica") or "").strip(),
        "observacoes": (data.get("observacoes") or "").strip(),
    }

    ncm_norm = normalize_ncm(data.get("ncm"))
    with get_conn() as conn:
        # valida obrigatórios mínimos
        if not payload["embalagem_code"] or not payload["cliente_id"] or not payload["material"]:
            return bad_request("Preencha Código, Cliente e Material.")
        # valida NCM se informado
        ok, msg = validate_ncm_or_none(conn, ncm_norm)
        if not ok:
            return bad_request(msg)
        if ncm_norm:
            payload["ncm"] = ncm_norm

        try:
            eid = safe_insert(conn, "embalagem_master", payload)
            conn.commit()
        except sqlite3.IntegrityError as e:
            # ex.: idxu_emb_code_rev ou outras constraints
            return bad_request("Falha ao criar embalagem (restrição/único).", {"detail": str(e)})

        row = conn.execute("SELECT * FROM embalagem_master WHERE id=?", (eid,)).fetchone()
        return jsonify(dict(row)), 201


# ==========================
# PEDIDOS (REST)
# ==========================
@app.route("/api/pedidos", methods=["GET"])
def api_pedidos_list():
        with get_conn() as conn:
                rows = conn.execute("""
                        SELECT p.*, c.razao_social AS cliente_nome,
                                     COALESCE((SELECT SUM(i.qtd) FROM pedido_itens i WHERE i.pedido_id = p.id), 0) AS quantidade_un,
                                     COALESCE(col.nome, p.representante_nome) AS representante_nome_exibicao,
                                     -- exib_total: se houver pelo menos 1 item usa soma(qtd*preco_unit); caso contrário tenta preco_base*quantidade_planejada
                                     CASE
                                         WHEN EXISTS(SELECT 1 FROM pedido_itens i2 WHERE i2.pedido_id = p.id)
                                             THEN (
                                                 SELECT ROUND(COALESCE(SUM(i3.qtd * COALESCE(i3.preco_unit,0)),0), 2)
                                                 FROM pedido_itens i3 WHERE i3.pedido_id = p.id
                                             )
                                         WHEN p.preco_base IS NOT NULL AND p.quantidade_planejada IS NOT NULL
                                             THEN ROUND(p.preco_base * p.quantidade_planejada, 2)
                                         ELSE p.preco_total
                                     END AS exib_total
                        FROM pedidos p
                        LEFT JOIN clientes c ON c.id = p.cliente_id
                        LEFT JOIN colaboradores col ON col.id = p.representante_id
                        ORDER BY p.id DESC
                """).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            # Normaliza campo de exibição único
            d['representante_nome'] = d.pop('representante_nome_exibicao', None)
            # Se preco_total estiver divergente de exib_total (e exib_total calculável), podemos exibir exib_total na lista
            d['exib_total'] = d.get('exib_total')
            out.append(d)
        return jsonify(out)

@app.route("/api/pedidos", methods=["POST"])
@login_required
@require_roles("pcp","operador","admin")  # operador opcional caso deseje permitir
def api_pedidos_create():
    data = request.json or {}
    cliente_id = data.get("cliente_id")
    if not cliente_id:
        return bad_request("cliente_id obrigatório")
    data_prevista = data.get("data_prevista")
    regime_venda = (data.get("regime_venda") or "").strip()
    with get_conn() as conn:
        # código sequencial
        numero = gerar_codigo_pedido(conn)
        # emissão agora (yyyy-mm-dd)
        from datetime import date
        data_emissao = date.today().isoformat()
        representante_nome = data.get("representante_nome")
        quantidade_planejada = data.get("quantidade_planejada")
        preco_base = data.get("preco_base")
        preco_total = data.get("preco_total")
        # Nova lógica: se não veio preco_total mas temos preco_base e quantidade_planejada -> multiplicar.
        if preco_total is None and preco_base is not None and quantidade_planejada:
            try:
                preco_total = float(preco_base) * float(quantidade_planejada)
            except Exception:
                preco_total = preco_base  # fallback mínimo
        elif preco_total is None and preco_base is not None:
            # Sem quantidade_planejada ainda: deixa null (será recalculado após itens ou quando quantidade aparecer)
            preco_total = None
        cur = conn.execute("""
            INSERT INTO pedidos(
              cliente_id, numero_pedido, data_emissao, data_prevista,
              quantidade_tipo, status, preco_total, margem_toler_percent, ncm,
              representante_id, regime_venda, comissao_percent, condicoes_comerciais,
              representante_nome, quantidade_planejada, embalagem_code, preco_base
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            cliente_id, numero, data_emissao, data_prevista,
            data.get("quantidade_tipo") or "UN", "RASCUNHO", preco_total,
            data.get("margem_toler_percent", 0), data.get("ncm"),
            data.get("representante_id"), regime_venda, data.get("comissao_percent"), data.get("condicoes_comerciais"),
            representante_nome, quantidade_planejada, data.get("embalagem_code"), preco_base
        ))
        pid = cur.lastrowid
        # log
        try:
            conn.execute(
                "INSERT INTO pedido_logs(pedido_id,user_id,acao,detalhe_json) VALUES (?,?,?,?)",
                (pid, session.get("user_id"), "CREATED", json.dumps({"numero": numero}))
            )
        except Exception:
            pass
        row = conn.execute("SELECT * FROM pedidos WHERE id=?", (pid,)).fetchone()
        return jsonify(dict(row)), 201

@app.route("/api/pedidos/<int:pedido_id>", methods=["GET"])
def api_pedidos_detail(pedido_id):
    with get_conn() as conn:
        pedido = conn.execute("SELECT * FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        if not pedido:
            return jsonify({"error": "pedido não encontrado"}), 404
        itens = conn.execute("SELECT * FROM pedido_itens WHERE pedido_id=?", (pedido_id,)).fetchall()
        logs = conn.execute("SELECT * FROM pedido_logs WHERE pedido_id=? ORDER BY id ASC", (pedido_id,)).fetchall()
        return jsonify({
            "pedido": dict(pedido),
            "itens": [dict(i) for i in itens],
            "logs": [dict(l) for l in logs]
        })

@app.route("/api/pedidos/<int:pedido_id>", methods=["PATCH"])
@login_required
@require_roles("pcp","operador","admin")
def api_pedidos_update(pedido_id):
    """Atualiza campos comerciais básicos do pedido.
    Regras:
      - Permitido editar somente enquanto status = RASCUNHO (futuro: talvez PLANEJADO).
      - Lista de campos permitidos limitada (protege consistência de métricas/itens).
      - Loga diffs em pedido_logs (acao = UPDATED).
    """
    data = request.json or {}
    allowed_fields = {
        "cliente_id", "data_prevista", "regime_venda", "comissao_percent",
        "representante_nome", "quantidade_planejada", "condicoes_comerciais",
        "embalagem_code", "preco_base", "preco_total", "quantidade_tipo", "ncm", "margem_toler_percent"
    }
    # Normalização simples
    clean = {k: v for k, v in data.items() if k in allowed_fields}
    if not clean:
        return bad_request("Nenhum campo permitido para atualização")
    with get_conn() as conn:
        row_old = conn.execute("SELECT * FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        if not row_old:
            return jsonify({"error": "pedido não encontrado"}), 404
        if row_old["status"] not in ("RASCUNHO",):
            return bad_request("Pedido não pode mais ser editado (status atual = %s)" % row_old["status"])
        # Ajustes derivados: se preco_base mudou e não há itens, podemos replicar em preco_total se não veio explicitamente.
        itens_count = conn.execute("SELECT COUNT(1) c FROM pedido_itens WHERE pedido_id=?", (pedido_id,)).fetchone()[0]
        if "preco_base" in clean and "preco_total" not in clean and itens_count == 0:
            clean["preco_total"] = clean["preco_base"]
        # Monta SET dinâmico
        sets = []
        params = []
        for k, v in clean.items():
            sets.append(f"{k}=?")
            params.append(v)
        params.append(pedido_id)
        if sets:
            conn.execute(f"UPDATE pedidos SET {', '.join(sets)} WHERE id=?", params)
        row_new = conn.execute("SELECT * FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        # Calcula diffs
        changed = {}
        for k in clean.keys():
            ov = row_old[k]
            nv = row_new[k]
            # comparação tolerante a tipos numéricos/strings
            if (ov is None and nv is not None) or (ov is not None and nv is None) or (str(ov) != str(nv)):
                changed[k] = {"old": ov, "new": nv}
        if changed:
            try:
                conn.execute(
                    "INSERT INTO pedido_logs(pedido_id,user_id,acao,detalhe_json) VALUES (?,?,?,?)",
                    (pedido_id, session.get("user_id"), "UPDATED", json.dumps({"fields": changed}))
                )
            except Exception:
                pass
        # Se itens_count == 0 e alteramos preco_base, quantidade_planejada ou quantidade_tipo -> recalcular total
        trigger_recalc_keys = {"preco_base", "quantidade_planejada", "quantidade_tipo"}
        if itens_count == 0 and trigger_recalc_keys.intersection(changed.keys()):
            old_total = row_old["preco_total"]
            new_total = _recalc_pedido_totais(conn, pedido_id)
            if new_total is not None and new_total != old_total:
                try:
                    conn.execute(
                        "INSERT INTO pedido_logs(pedido_id,user_id,acao,detalhe_json) VALUES (?,?,?,?)",
                        (pedido_id, session.get("user_id"), "RECALC_TOTAL", json.dumps({"de": old_total, "para": new_total, "motivo": "patch campos base sem itens"}))
                    )
                except Exception:
                    pass
                row_new = conn.execute("SELECT * FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        return jsonify(dict(row_new))

@app.route("/api/pedidos/<int:pedido_id>/itens", methods=["POST"])
@login_required
@require_roles("pcp","operador","admin")
def api_pedido_itens_add(pedido_id):
    data = request.json or {}
    with get_conn() as conn:
        ped = conn.execute("SELECT * FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        if not ped:
            return jsonify({"error": "pedido não encontrado"}), 404
        if (ped["status"] or "").upper() != "RASCUNHO":
            return bad_request("Pedido não está em RASCUNHO (itens bloqueados)")
        # Carrega embalagem p/ snapshot
        emb = conn.execute(
            "SELECT * FROM embalagem_master WHERE embalagem_code=? AND IFNULL(rev,'')=IFNULL(?, '')",
            (data.get("embalagem_code"), data.get("rev"))
        ).fetchone()
        if not emb:
            return bad_request("Embalagem não encontrada para snapshot")
        descricao = (data.get("descricao") or emb["embalagem_code"])  # fallback simples
        payload = {
            "pedido_id": pedido_id,
            "embalagem_code": emb["embalagem_code"],
            "rev": emb["rev"],
            "descricao": descricao,
            "qtd": data.get("qtd"),
            "qtd_tipo": data.get("qtd_tipo") or "UN",
            "preco_unit": data.get("preco_unit"),
            "preco_kg": data.get("preco_kg"),
            "peso_unit_kg": data.get("peso_unit_kg"),
            "margem_toler_percent": data.get("margem_toler_percent"),
            "snapshot_material": emb["material"],
            "snapshot_espessura_um": emb["espessura_um"],
            "snapshot_largura_mm": emb["largura_mm"],
            "snapshot_altura_mm": emb["altura_mm"],
            "snapshot_sanfona_mm": emb["sanfona_mm"],
            "snapshot_aba_mm": emb["aba_mm"],
            "snapshot_fita_tipo": emb["fita_tipo"],
            "snapshot_tratamento": 1 if (emb["transparencia"] or 0) > -9999 and emb["transparencia"] is not None else 0,
            "snapshot_tratamento_dinas": None,  # não temos campo explícito dinas na tabela ainda
            "snapshot_impresso": emb["impresso"],
            "anel_extrusao": data.get("anel_extrusao"),
            "status_impressao": data.get("status_impressao") or "rascunho",
            "extrusado": 0,
            "qtde_extrusada_kg": None,
        }
        cols = list(payload.keys())
        vals = [payload[c] for c in cols]
        sql = f"INSERT INTO pedido_itens ({', '.join(cols)}) VALUES ({', '.join(['?']*len(cols))})"
        cur = conn.execute(sql, vals)
        iid = cur.lastrowid
        try:
            conn.execute(
                "INSERT INTO pedido_logs(pedido_id,user_id,acao,detalhe_json) VALUES (?,?,?,?)",
                (pedido_id, session.get("user_id"), "ITEM_ADDED", json.dumps({"item_id": iid, "embalagem_code": emb["embalagem_code"]}))
            )
        except Exception:
            pass
        old_total = conn.execute("SELECT preco_total FROM pedidos WHERE id=?", (pedido_id,)).fetchone()[0]
        new_total = _recalc_pedido_totais(conn, pedido_id)
        if new_total is not None and new_total != old_total:
            try:
                conn.execute(
                    "INSERT INTO pedido_logs(pedido_id,user_id,acao,detalhe_json) VALUES (?,?,?,?)",
                    (pedido_id, session.get("user_id"), "RECALC_TOTAL", json.dumps({"de": old_total, "para": new_total}))
                )
            except Exception:
                pass
        row = conn.execute("SELECT * FROM pedido_itens WHERE id=?", (iid,)).fetchone()
        return jsonify(dict(row)), 201

@app.route("/api/pedidos/<int:pedido_id>/itens/<int:item_id>", methods=["DELETE"])
@login_required
@require_roles("pcp","operador","admin")
def api_pedido_item_delete(pedido_id: int, item_id: int):
    with get_conn() as conn:
        ped = conn.execute("SELECT status FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        if not ped:
            return jsonify({"error": "pedido não encontrado"}), 404
        if (ped["status"] or "").upper() != "RASCUNHO":
            return bad_request("Itens só podem ser removidos em RASCUNHO")
        ex = conn.execute("SELECT id FROM pedido_itens WHERE id=? AND pedido_id=?", (item_id, pedido_id)).fetchone()
        if not ex:
            return jsonify({"error": "item não encontrado"}), 404
        conn.execute("DELETE FROM pedido_itens WHERE id=?", (item_id,))
        try:
            conn.execute(
                "INSERT INTO pedido_logs(pedido_id,user_id,acao,detalhe_json) VALUES (?,?,?,?)",
                (pedido_id, session.get("user_id"), "ITEM_DELETED", json.dumps({"item_id": item_id}))
            )
        except Exception:
            pass
        old_total = conn.execute("SELECT preco_total FROM pedidos WHERE id=?", (pedido_id,)).fetchone()[0]
        new_total = _recalc_pedido_totais(conn, pedido_id)
        if new_total is not None and new_total != old_total:
            try:
                conn.execute(
                    "INSERT INTO pedido_logs(pedido_id,user_id,acao,detalhe_json) VALUES (?,?,?,?)",
                    (pedido_id, session.get("user_id"), "RECALC_TOTAL", json.dumps({"de": old_total, "para": new_total}))
                )
            except Exception:
                pass
        return ("", 204)

@app.route("/api/pedidos/<int:pedido_id>/itens/<int:item_id>", methods=["PATCH"])
@login_required
@require_roles("pcp","operador","admin")
def api_pedido_item_update(pedido_id: int, item_id: int):
    """Atualiza campos permitidos de um item.

    Regras:
      - Campos snapshot_* jamais alteráveis.
      - While pedido em RASCUNHO: pode alterar descricao, qtd, qtd_tipo, preco_unit, preco_kg, peso_unit_kg,
        margem_toler_percent, status_impressao, anel_extrusao.
      - Após RASCUNHO (APROVADO ou EM_EXECUCAO...): somente status_impressao e anel_extrusao.
      - Itens não podem ser alterados em CONCLUIDO ou CANCELADO.
    """
    data = request.json or {}
    with get_conn() as conn:
        ped = conn.execute("SELECT status FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        if not ped:
            return jsonify({"error": "pedido não encontrado"}), 404
        pstatus = (ped["status"] or "").upper()
        if pstatus in {"CONCLUIDO", "CANCELADO"}:
            return bad_request("Pedido não permite alterações em itens nesse status")
        item = conn.execute("SELECT * FROM pedido_itens WHERE id=? AND pedido_id=?", (item_id, pedido_id)).fetchone()
        if not item:
            return jsonify({"error": "item não encontrado"}), 404

        # Campos permitidos conforme status
        base_allowed = {"status_impressao", "anel_extrusao"}
        draft_extra = {"descricao", "qtd", "qtd_tipo", "preco_unit", "preco_kg", "peso_unit_kg", "margem_toler_percent"}
        if pstatus == "RASCUNHO":
            allowed = base_allowed | draft_extra
        else:
            allowed = base_allowed

        # Filtrar payload
        updates: dict[str, object] = {}
        blocked: list[str] = []
        for k, v in data.items():
            if k.startswith("snapshot_"):
                blocked.append(k)
                continue
            if k in allowed:
                updates[k] = v
            else:
                if k not in {"pedido_id", "id"}:
                    blocked.append(k)
        if not updates:
            return bad_request("Nenhum campo permitido para atualização", {"bloqueados": blocked})

        # Montar SET dinâmico
        sets = []
        values = []
        for k, v in updates.items():
            sets.append(f"{k}=?")
            values.append(v)
        values.append(item_id)
        sql = f"UPDATE pedido_itens SET {', '.join(sets)} WHERE id=?"
        conn.execute(sql, tuple(values))

        # Diff para log
        diffs = {}
        for k in updates:
            old_val = item[k]
            new_val = updates[k]
            if old_val != new_val:
                diffs[k] = {"de": old_val, "para": new_val}
        if diffs:
            try:
                conn.execute(
                    "INSERT INTO pedido_logs(pedido_id,user_id,acao,detalhe_json) VALUES (?,?,?,?)",
                    (pedido_id, session.get("user_id"), "ITEM_UPDATED", json.dumps({"item_id": item_id, "changes": diffs}))
                )
            except Exception:
                pass
        old_total = conn.execute("SELECT preco_total FROM pedidos WHERE id=?", (pedido_id,)).fetchone()[0]
        new_total = _recalc_pedido_totais(conn, pedido_id)
        if new_total is not None and new_total != old_total:
            try:
                conn.execute(
                    "INSERT INTO pedido_logs(pedido_id,user_id,acao,detalhe_json) VALUES (?,?,?,?)",
                    (pedido_id, session.get("user_id"), "RECALC_TOTAL", json.dumps({"de": old_total, "para": new_total}))
                )
            except Exception:
                pass
        row = conn.execute("SELECT * FROM pedido_itens WHERE id=?", (item_id,)).fetchone()
        return jsonify(dict(row))

@app.route("/api/pedidos/<int:pedido_id>/logs", methods=["GET"])
@login_required
def api_pedido_logs(pedido_id: int):
    with get_conn() as conn:
        ped = conn.execute("SELECT id FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        if not ped:
            return jsonify({"error": "pedido não encontrado"}), 404
        logs = conn.execute("SELECT * FROM pedido_logs WHERE pedido_id=? ORDER BY id ASC", (pedido_id,)).fetchall()
        return jsonify([dict(l) for l in logs])

@app.route("/api/pedidos/<int:pedido_id>/status", methods=["POST"])
@login_required
@require_roles("pcp","admin")
def api_pedido_change_status(pedido_id: int):
    data = request.json or {}
    novo = (data.get("status") or "").upper()
    allowed = {"RASCUNHO", "APROVADO", "EM_EXECUCAO", "CONCLUIDO", "CANCELADO"}
    if novo not in allowed:
        return bad_request("Status inválido")
    with get_conn() as conn:
        ped = conn.execute("SELECT status FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        if not ped:
            return jsonify({"error": "pedido não encontrado"}), 404
        atual = (ped["status"] or "").upper()
        # regras simples de transição (MVP)
        transicoes_validas = {
            "RASCUNHO": {"APROVADO", "CANCELADO"},
            "APROVADO": {"EM_EXECUCAO", "CANCELADO"},
            "EM_EXECUCAO": {"CONCLUIDO", "CANCELADO"},
            "CONCLUIDO": set(),
            "CANCELADO": set(),
        }
        if novo not in transicoes_validas.get(atual, set()):
            return bad_request("Transição de status não permitida", {"atual": atual, "novo": novo})
        conn.execute("UPDATE pedidos SET status=? WHERE id=?", (novo, pedido_id))
        try:
            conn.execute(
                "INSERT INTO pedido_logs(pedido_id,user_id,acao,detalhe_json) VALUES (?,?,?,?)",
                (pedido_id, session.get("user_id"), "STATUS_CHANGED", json.dumps({"de": atual, "para": novo}))
            )
        except Exception:
            pass
        # Recalcular totais ainda dentro da mesma conexão aberta
        _recalc_pedido_totais(conn, pedido_id)
        row = conn.execute("SELECT * FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        return jsonify(dict(row))

# ==========================
# PRODUÇÃO (Ordens de Produção simples MVP)
# ==========================
@app.route("/api/pedidos/<int:pedido_id>/ordens_producao", methods=["GET"])
@login_required
def api_op_list(pedido_id: int):
    """Lista ordens de produção (corte & solda) vinculadas ao pedido."""
    with get_conn() as conn:
        ped = conn.execute("SELECT id FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        if not ped:
            return jsonify({"error": "pedido não encontrado"}), 404
        rows = conn.execute("SELECT * FROM ordens_producao WHERE pedido_id=? ORDER BY id", (pedido_id,)).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route("/api/pedidos/<int:pedido_id>/ordens_producao", methods=["POST"])
@login_required
@require_roles("pcp","admin")
def api_op_create(pedido_id: int):
    """Cria ordem de produção básica.

    Regras MVP:
      - Pedido precisa estar APROVADO ou EM_EXECUCAO.
      - Ao criar a PRIMEIRA ordem, status do pedido muda para EM_EXECUCAO.
      - Log registrado com ação OP_CREATED.
    """
    data = request.json or {}
    with get_conn() as conn:
        ped = conn.execute("SELECT status FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        if not ped:
            return jsonify({"error":"pedido não encontrado"}), 404
        status_atual = (ped["status"] or "").upper()
        if status_atual not in {"APROVADO", "EM_EXECUCAO"}:
            return bad_request("Pedido precisa estar APROVADO para gerar ordem")
        payload = {
            "pedido_id": pedido_id,
            "numero": (data.get("numero") or "").strip() or None,
            "largura_mm": data.get("largura_mm"),
            "altura_mm": data.get("altura_mm"),
            "sanfona_mm": data.get("sanfona_mm"),
            "aba_mm": data.get("aba_mm"),
            "fita_tipo": data.get("fita_tipo"),
            "resistencia_mecanica": data.get("resistencia_mecanica"),
            "temp_solda_c": data.get("temp_solda_c"),
            "velocidade_corte_cpm": data.get("velocidade_corte_cpm"),
            "peso_min_bobina_kg": data.get("peso_min_bobina_kg"),
            "margem_erro_un_percent": data.get("margem_erro_un_percent"),
            "status": "planejada",
        }
        cols = list(payload.keys())
        vals = [payload[c] for c in cols]
        cur = conn.execute(
            f"INSERT INTO ordens_producao ({', '.join(cols)}) VALUES ({', '.join(['?']*len(cols))})",
            vals
        )
        op_id = cur.lastrowid
        try:
            conn.execute(
                "INSERT INTO pedido_logs(pedido_id,user_id,acao,detalhe_json) VALUES (?,?,?,?)",
                (pedido_id, session.get("user_id"), "OP_CREATED", json.dumps({"ordem_producao_id": op_id}))
            )
        except Exception:
            pass
        # Se for a primeira ordem e pedido ainda APROVADO -> muda para EM_EXECUCAO
        if status_atual == "APROVADO":
            total_ops = conn.execute("SELECT COUNT(1) FROM ordens_producao WHERE pedido_id=?", (pedido_id,)).fetchone()[0]
            if total_ops == 1:
                conn.execute("UPDATE pedidos SET status='EM_EXECUCAO' WHERE id=?", (pedido_id,))
                try:
                    conn.execute(
                        "INSERT INTO pedido_logs(pedido_id,user_id,acao,detalhe_json) VALUES (?,?,?,?)",
                        (pedido_id, session.get("user_id"), "STATUS_CHANGED", json.dumps({"de": "APROVADO", "para": "EM_EXECUCAO", "auto": True}))
                    )
                except Exception:
                    pass
        row = conn.execute("SELECT * FROM ordens_producao WHERE id=?", (op_id,)).fetchone()
        return jsonify(dict(row)), 201

# ==========================
# QUALIDADE (QC genérico MVP)
# ==========================
@app.route("/api/pedidos/<int:pedido_id>/qc", methods=["GET"])
@login_required
def api_qc_list(pedido_id: int):
    with get_conn() as conn:
        ped = conn.execute("SELECT id FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        if not ped:
            return jsonify({"error":"pedido não encontrado"}), 404
        rows = conn.execute("SELECT * FROM qc_inspecoes WHERE referencia_id=? ORDER BY id", (pedido_id,)).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route("/api/pedidos/<int:pedido_id>/qc", methods=["POST"])
@login_required
@require_roles("qualidade","pcp","admin")
def api_qc_add(pedido_id: int):
    data = request.json or {}
    with get_conn() as conn:
        ped = conn.execute("SELECT id FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        if not ped:
            return jsonify({"error":"pedido não encontrado"}), 404
        payload = {
            "tipo": (data.get("tipo") or "QC").strip(),
            "referencia_id": pedido_id,
            "amostra": (data.get("amostra") or "").strip(),
            "resultado": (data.get("resultado") or "").strip(),
            "observacoes": (data.get("observacoes") or "").strip(),
            "fotos_json": json.dumps(data.get("fotos") or []),
        }
        cols = list(payload.keys())
        vals = [payload[c] for c in cols]
        cur = conn.execute(
            f"INSERT INTO qc_inspecoes ({', '.join(cols)}) VALUES ({', '.join(['?']*len(cols))})",
            vals
        )
        qid = cur.lastrowid
        try:
            conn.execute(
                "INSERT INTO pedido_logs(pedido_id,user_id,acao,detalhe_json) VALUES (?,?,?,?)",
                (pedido_id, session.get("user_id"), "QC_ADDED", json.dumps({"qc_id": qid, "tipo": payload["tipo"]}))
            )
        except Exception:
            pass
        row = conn.execute("SELECT * FROM qc_inspecoes WHERE id=?", (qid,)).fetchone()
        return jsonify(dict(row)), 201

# ==========================
# CÁLCULOS (REST)
# ==========================
@app.route("/api/pedidos/<int:pedido_id>/metrics", methods=["GET"])
@login_required
def api_pedido_metrics(pedido_id: int):
    """Retorna métricas derivadas do pedido.

    Métricas iniciais:
      - total_itens: quantidade de itens
      - valor_total: soma preco_unit * qtd (já existe em pedidos.preco_total; revalida)
      - total_qtd_un: soma de quantidades em UN
      - total_qtd_kg: soma direta em KG + conversão de UN usando peso_unit_kg
      - unidades_estimada_de_kg: para itens KG com peso_unit_kg definido
      - peso_estimado_total_kg: alias de total_qtd_kg
      - percentual_itens_impressos: itens com status_impressao = 'concluida' / total_itens
    Futuro: rendimento, sucata, avanço extrusão, avanço produção.
    """
    with get_conn() as conn:
        ped = conn.execute("SELECT * FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        if not ped:
            return jsonify({"error": "pedido não encontrado"}), 404
        itens = conn.execute("SELECT qtd, qtd_tipo, preco_unit, peso_unit_kg, status_impressao FROM pedido_itens WHERE pedido_id=?", (pedido_id,)).fetchall()
        total_itens = len(itens)
        valor_total_calc = 0.0
        total_qtd_un = 0.0
        total_qtd_kg = 0.0
        unidades_estimada_de_kg = 0.0
        concl_impressos = 0
        for it in itens:
            qtd = float(it["qtd"] or 0)
            preco_unit = float(it["preco_unit"] or 0)
            peso_unit = float(it["peso_unit_kg"] or 0)
            valor_total_calc += qtd * preco_unit
            if (it["qtd_tipo"] or "UN").upper() == "UN":
                total_qtd_un += qtd
                if peso_unit > 0:
                    total_qtd_kg += qtd * peso_unit
            else:
                # KG direto
                total_qtd_kg += qtd
                if peso_unit > 0:
                    unidades_estimada_de_kg += qtd / peso_unit
            if (it["status_impressao"] or "").lower() == "concluida":
                concl_impressos += 1
        percentual_itens_impressos = (concl_impressos / total_itens * 100) if total_itens else 0.0
        return jsonify({
            "pedido_id": pedido_id,
            "valor_total_calc": valor_total_calc,
            "valor_total_registrado": ped["preco_total"],
            "total_itens": total_itens,
            "total_qtd_un": total_qtd_un,
            "total_qtd_kg": total_qtd_kg,
            "peso_estimado_total_kg": total_qtd_kg,
            "unidades_estimada_de_kg": unidades_estimada_de_kg,
            "percentual_itens_impressos": percentual_itens_impressos,
        })
@app.route("/calc/massa_unidade", methods=["POST"])
def api_massa_unidade():
    d = request.json or {}
    massa = massa_por_unidade(
        d["material"], d["esp_um"], d["largura_mm"], d["altura_mm"], d.get("sanfona_mm", 0), d.get("fator_extra", 0.0)
    )
    return jsonify({"massa_unidade_kg": round(massa, 6)})

@app.route("/calc/estimativa_unidades", methods=["POST"])
def api_estimativa_unidades():
    d = request.json or {}
    un = unidades_estimadas_por_peso(d["peso_kg"], d["massa_unidade_kg"])
    return jsonify({"unidades_estimadas": int(un)})

@app.route("/calc/unidades_minimas", methods=["POST"])
def api_unidades_minimas():
    d = request.json or {}
    return jsonify({"unidades_minimas": unidades_minimas(d["qtd_solicitada_un"], d["toler_percent"])})

# ==========================
# IMPRESSÃO (REST)
# ==========================
@app.route("/impressao/ordens", methods=["POST"])
def impressao_ordem_create():
    d = request.json or {}
    with get_conn() as conn:
        cur = conn.execute("""
          INSERT INTO ordens_impressao(
            pedido_id, numero, bobina_crua_lote, cores, tinta_tipo, cliche_ref,
            velocidade_alvo_mpm, perdas_previstas_percent, registro_toler_mm, status
          ) VALUES (?,?,?,?,?,?,?,?,?, 'ABERTA')
        """, (
            d["pedido_id"], d.get("numero"), d.get("bobina_crua_lote"),
            d.get("cores"), d.get("tinta_tipo"), d.get("cliche_ref"),
            d.get("velocidade_alvo_mpm"), d.get("perdas_previstas_percent"),
            d.get("registro_toler_mm")
        ))
        oid = cur.lastrowid
        row = conn.execute("SELECT * FROM ordens_impressao WHERE id=?", (oid,)).fetchone()
        return jsonify(dict(row)), 201

@app.route("/impressao/ordens", methods=["GET"])
def impressao_ordem_list():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM ordens_impressao ORDER BY id DESC").fetchall()
        return jsonify([dict(r) for r in rows])

@app.route("/impressao/recebimentos", methods=["POST"])
def recebimento_bobina_impressa_create():
    d = request.json or {}
    with get_conn() as conn:
        cur = conn.execute("""
          INSERT INTO bobinas_impressas(
            ordem_impressao_id, bobina_crua_id, etiqueta, largura_mm,
            peso_bruto_kg, tara_tubo_kg, tara_embalagem_kg,
            sucata_kg, sucata_motivo, qc2_status, local_estoque
          ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            d["ordem_impressao_id"], d.get("bobina_crua_id"),
            d.get("etiqueta"), d.get("largura_mm"),
            d["peso_bruto_kg"], d.get("tara_tubo_kg", 0.0), d.get("tara_embalagem_kg", 0.0),
            d.get("sucata_kg", 0.0), d.get("sucata_motivo"),
            d.get("qc2_status", "PENDENTE"), d.get("local_estoque")
        ))
        bid = cur.lastrowid
        row = conn.execute("SELECT * FROM bobinas_impressas WHERE id=?", (bid,)).fetchone()
        # ENTRADA no estoque com peso líquido
        conn.execute("""
          INSERT INTO estoque_bobinas_impressas_mov(bobinas_impressa_id, tipo, qtd_kg, referencia)
          VALUES (?, 'ENTRADA', ?, 'Recebimento pós-impressão')
        """, (bid, row["peso_liquido_kg"] or 0.0))
        return jsonify(dict(row)), 201

@app.route("/impressao/recebimentos", methods=["GET"])
def recebimento_bobina_impressa_list():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM bobinas_impressas ORDER BY id DESC").fetchall()
        return jsonify([dict(r) for r in rows])

@app.route("/impressao/ordens/<int:oid>/status", methods=["POST"])
def impressao_ordem_status(oid):
    d = request.json or {}
    novo = d.get("status")
    if novo not in ("ABERTA", "EM_EXECUCAO", "CONCLUIDA"):
        return bad_request("status inválido")
    with get_conn() as conn:
        ex = conn.execute("SELECT id FROM ordens_impressao WHERE id=?", (oid,)).fetchone()
        if not ex:
            return jsonify({"error": "ordem não encontrada"}), 404
        conn.execute("UPDATE ordens_impressao SET status=? WHERE id=?", (novo, oid))
        row = conn.execute("SELECT * FROM ordens_impressao WHERE id=?", (oid,)).fetchone()
        return jsonify(dict(row))

# ==========================
# GATE (Elegibilidade para Corte & Solda) (REST)
# ==========================
@app.route("/gates/corte_solda/elegibilidade", methods=["POST"])
def gate_corte_solda_elegibilidade():
    d = request.json or {}
    with get_conn() as conn:
        rows = conn.execute("""
          SELECT bi.id, bi.qc2_status,
                 COALESCE(bi.peso_liquido_kg,0) - COALESCE(SUM(CASE WHEN mov.tipo='SAIDA' THEN mov.qtd_kg ELSE 0 END),0) AS saldo_kg
          FROM bobinas_impressas bi
          LEFT JOIN estoque_bobinas_impressas_mov mov ON mov.bobinas_impressa_id = bi.id
          WHERE bi.ordem_impressao_id=?
          GROUP BY bi.id
        """, (d["ordem_impressao_id"],)).fetchall()
        elegivel = any(r["qc2_status"] == "APROVADA" and (r["saldo_kg"] or 0) >= float(d.get("peso_min_kg", 0)) for r in rows)
        return jsonify({"elegivel": bool(elegivel), "bobinas": [dict(r) for r in rows]})

# ==========================
# PRODUÇÃO — Corte & Solda (REST)
# ==========================
@app.route("/producao/ordens", methods=["POST"])
def producao_ordem_create():
    d = request.json or {}
    with get_conn() as conn:
        cur = conn.execute("""
          INSERT INTO ordens_producao(
            pedido_id, numero, largura_mm, altura_mm, sanfona_mm, aba_mm, fita_tipo,
            resistencia_mecanica, temp_solda_c, velocidade_corte_cpm,
            peso_min_bobina_kg, margem_erro_un_percent, status
          ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'ABERTA')
        """, (
            d["pedido_id"], d.get("numero"),
            d["largura_mm"], d["altura_mm"], d.get("sanfona_mm", 0), d.get("aba_mm", 0), d["fita_tipo"],
            d.get("resistencia_mecanica"), d.get("temp_solda_c"), d.get("velocidade_corte_cpm"),
            d.get("peso_min_bobina_kg"), d.get("margem_erro_un_percent")
        ))
        opid = cur.lastrowid
        row = conn.execute("SELECT * FROM ordens_producao WHERE id=?", (opid,)).fetchone()
        return jsonify(dict(row)), 201

@app.route("/producao/ordens/<int:opid>/status", methods=["POST"])
def producao_ordem_status(opid):
    d = request.json or {}
    if d.get("status") not in ("ABERTA", "EM_EXECUCAO", "EM_INSPECAO", "CONCLUIDA"):
        return bad_request("status inválido")
    with get_conn() as conn:
        ex = conn.execute("SELECT id FROM ordens_producao WHERE id=?", (opid,)).fetchone()
        if not ex:
            return jsonify({"error": "ordem não encontrada"}), 404
        conn.execute("UPDATE ordens_producao SET status=? WHERE id=?", (d["status"], opid))
        row = conn.execute("SELECT * FROM ordens_producao WHERE id=?", (opid,)).fetchone()
        return jsonify(dict(row))

@app.route("/producao/ordens/<int:opid>/apontar", methods=["POST"])
def producao_apontar(opid):
    d = request.json or {}
    with get_conn() as conn:
        cur = conn.execute("""
          INSERT INTO producao_apontamentos(
            ordem_producao_id, bobina_impressa_id, peso_consumido_kg, peso_saida_kg, sucata_kg, sucata_motivo
          ) VALUES (?,?,?,?,?,?)
        """, (
            opid, d.get("bobina_impressa_id"), d.get("peso_consumido_kg", 0.0),
            d.get("peso_saida_kg", 0.0), d.get("sucata_kg", 0.0), d.get("sucata_motivo")
        ))
        aid = cur.lastrowid

        # baixa de estoque
        if d.get("bobina_impressa_id") and d.get("peso_consumido_kg", 0) > 0:
            referencia = f"Consumo Corte & Solda (OP {opid})"
            conn.execute("""
              INSERT INTO estoque_bobinas_impressas_mov(bobinas_impressa_id, tipo, qtd_kg, referencia)
              VALUES (?, 'SAIDA', ?, ?)
            """, (d["bobina_impressa_id"], d["peso_consumido_kg"], referencia))

        row = conn.execute("SELECT * FROM producao_apontamentos WHERE id=?", (aid,)).fetchone()
        return jsonify(dict(row)), 201

# ==========================
# QUALIDADE (REST genérico)
# ==========================
@app.route("/qc", methods=["POST"])
def qc_create():
    d = request.json or {}
    if d.get("tipo") not in ("QC1", "QC2", "QC3", "QC4"):
        return bad_request("tipo inválido")
    with get_conn() as conn:
        cur = conn.execute("""
          INSERT INTO qc_inspecoes(tipo, referencia_id, amostra, resultado, observacoes, fotos_json)
          VALUES (?,?,?,?,?,?)
        """, (
            d["tipo"], d["referencia_id"], d.get("amostra"),
            d["resultado"], d.get("observacoes"), json.dumps(d.get("fotos", []), ensure_ascii=False)
        ))
        qid = cur.lastrowid
        row = conn.execute("SELECT * FROM qc_inspecoes WHERE id=?", (qid,)).fetchone()
        return jsonify(dict(row)), 201

# ==========================
# EXPEDIÇÃO (REST)
# ==========================
@app.route("/api/expedicoes", methods=["POST"])
def api_expedicao_create():
    d = request.json or {}
    if d.get("modal") not in ("transportadora", "veiculo_proprio"):
        return bad_request("modal inválido")
    with get_conn() as conn:
        cur = conn.execute("""
          INSERT INTO expedicoes(
            pedido_id, modal, transportadora, destino, data_saida,
            veiculo_motorista, veiculo_placa, rota_bairros, comprovante_path, romaneio_json, status
          ) VALUES (?,?,?,?,?,?,?,?,?,?, 'PENDENTE')
        """, (
            d["pedido_id"], d["modal"], d.get("transportadora"), d.get("destino"), d.get("data_saida"),
            d.get("veiculo_motorista"), d.get("veiculo_placa"), d.get("rota_bairros"),
            d.get("comprovante_path"), json.dumps(d.get("romaneio", []), ensure_ascii=False)
        ))
        xid = cur.lastrowid
        row = conn.execute("SELECT * FROM expedicoes WHERE id=?", (xid,)).fetchone()
        return jsonify(dict(row)), 201

@app.route("/api/expedicoes/<int:xid>/liberar", methods=["POST"])
def api_expedicao_liberar(xid):
    with get_conn() as conn:
        ex = conn.execute("SELECT * FROM expedicoes WHERE id=?", (xid,)).fetchone()
        if not ex:
            return jsonify({"error": "expedição não encontrada"}), 404
        conn.execute("UPDATE expedicoes SET status='LIBERADA' WHERE id=?", (xid,))
        row = conn.execute("SELECT * FROM expedicoes WHERE id=?", (xid,)).fetchone()
        return jsonify(dict(row))

# ==========================
# COLABORADORES (REST) — GET com JOIN em parceiros e busca por parceiro
# ==========================
@app.route("/api/colaboradores", methods=["GET"])
def api_colaboradores_list():
    ativo = request.args.get("ativo")
    setor = request.args.get("setor")
    vinculo = request.args.get("vinculo")
    parceiro_id = request.args.get("parceiro_id")
    acesso_nivel = request.args.get("acesso_nivel")
    q = request.args.get("q")

    sql = """
        SELECT c.*,
               p.razao_social AS parceiro_nome,
               p.id AS parceiro_id
        FROM colaboradores c
        LEFT JOIN parceiros p ON p.id = c.parceiro_id
        WHERE 1=1
    """
    params = []

    if ativo is not None:
        sql += " AND c.ativo=?"
        params.append(int(ativo))
    if setor:
        sql += " AND c.setor=?"
        params.append(setor)
    if vinculo:
        sql += " AND c.vinculo=?"
        params.append(vinculo)
    if parceiro_id:
        sql += " AND c.parceiro_id=?"
        params.append(int(parceiro_id))
    if acesso_nivel:
        sql += " AND c.acesso_nivel=?"
        params.append(acesso_nivel)
    if q:
        like = f"%{q}%"
        sql += " AND (c.nome LIKE ? OR c.cpf LIKE ? OR c.email LIKE ? OR c.telefone LIKE ?)"
        params.extend([like, like, like, like])

    sql += " ORDER BY c.nome ASC"

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return jsonify([dict(r) for r in rows])



@app.route("/api/colaboradores", methods=["POST"])
def api_colaboradores_create():
    d = request.json or {}
    nome = (d.get("nome") or "").strip()
    if not nome:
        return bad_request("nome é obrigatório")

    cpf = only_digits(d.get("cpf") or "") or None
    email = (d.get("email") or "").strip() or None
    telefone = (d.get("telefone") or "").strip() or None
    cidade = (d.get("cidade") or "").strip() or None
    estado = (d.get("estado") or "").strip().upper()[:2] or None
    cep = only_digits(d.get("cep") or "") or None
    cargo = (d.get("cargo") or "").strip() or None
    setor = (d.get("setor") or "producao").strip()
    vinculo = (d.get("vinculo") or "CLT").strip()
    parceiro_id = d.get("parceiro_id")
    ativo = int(d.get("ativo")) if d.get("ativo") is not None else 1
    foto_url = (d.get("foto_url") or "").strip() or None
    data_admissao = (d.get("data_admissao") or "").strip() or None
    pis = (d.get("pis") or "").strip() or None
    ctps_numero = (d.get("ctps_numero") or "").strip() or None
    ctps_serie = (d.get("ctps_serie") or "").strip() or None
    observacoes = (d.get("observacoes") or "").strip() or None

    usuario_id = d.get("usuario_id")
    acesso_nivel = (d.get("acesso_nivel") or "nenhum").strip()

    # Regras de negócio
    if vinculo == "PJ" and not parceiro_id:
        return bad_request("Para vínculo PJ é obrigatório informar parceiro_id.")
    if acesso_nivel != "nenhum" and not usuario_id:
        return bad_request("Para conceder acesso ao sistema informe usuario_id válido (ou crie o usuário antes).")

    with get_conn() as conn:
        # valida parceiro se informado
        if parceiro_id:
            ex_p = conn.execute("SELECT id FROM parceiros WHERE id=?", (parceiro_id,)).fetchone()
            if not ex_p:
                return bad_request("parceiro_id inválido (parceiro não encontrado).")

        # valida usuario se for exigir acesso
        if usuario_id:
            ex_u = conn.execute("SELECT id FROM usuarios WHERE id=? AND ativo=1", (usuario_id,)).fetchone()
            if not ex_u:
                return bad_request("usuario_id inválido (usuário não encontrado ou inativo).")

        payload = {
            "nome": nome,
            "cpf": cpf,
            "email": email,
            "telefone": telefone,
            "cidade": cidade,
            "estado": estado,
            "cep": cep,
            "cargo": cargo,
            "setor": setor,
            "vinculo": vinculo,
            "parceiro_id": parceiro_id,
            "ativo": ativo,
            "foto_url": foto_url,
            "data_admissao": data_admissao,
            "pis": pis,
            "ctps_numero": ctps_numero,
            "ctps_serie": ctps_serie,
            "observacoes": observacoes,
            "usuario_id": usuario_id,
            "acesso_nivel": acesso_nivel,
        }

        try:
            cid = safe_insert(conn, "colaboradores", payload)
        except sqlite3.IntegrityError as e:
            # CPF UNIQUE, constraint parceiro/vinculo etc.
            return bad_request("Falha ao inserir colaborador (violação de restrição).", {"detail": str(e)})

        row = conn.execute("SELECT * FROM colaboradores WHERE id=?", (cid,)).fetchone()
        return jsonify(dict(row)), 201

@app.route("/api/colaboradores/<int:cid>", methods=["PUT", "PATCH"])
def api_colaboradores_update(cid: int):
    d = request.json or {}
    # mesmas validações chave
    vinculo = (d.get("vinculo") or "").strip() or None
    parceiro_id = d.get("parceiro_id")
    usuario_id = d.get("usuario_id")
    acesso_nivel = (d.get("acesso_nivel") or "").strip() or None

    with get_conn() as conn:
        ex = conn.execute("SELECT * FROM colaboradores WHERE id=?", (cid,)).fetchone()
        if not ex:
            return jsonify({"error": "colaborador não encontrado"}), 404

        if vinculo == "PJ" and parceiro_id is None and ex["parceiro_id"] is None:
            return bad_request("Para vínculo PJ é obrigatório informar parceiro_id.")

        if acesso_nivel and acesso_nivel != "nenhum":
            uid = usuario_id if usuario_id is not None else ex["usuario_id"]
            if not uid:
                return bad_request("Para conceder acesso ao sistema informe usuario_id válido (ou crie o usuário antes).")
            ex_u = conn.execute("SELECT id FROM usuarios WHERE id=? AND ativo=1", (uid,)).fetchone()
            if not ex_u:
                return bad_request("usuario_id inválido (usuário não encontrado ou inativo).")

        # valida parceiro se informado
        if parceiro_id:
            ex_p = conn.execute("SELECT id FROM parceiros WHERE id=?", (parceiro_id,)).fetchone()
            if not ex_p:
                return bad_request("parceiro_id inválido (parceiro não encontrado).")

        payload = {
            "nome": (d.get("nome") or "").strip() or ex["nome"],
            "cpf": only_digits(d.get("cpf") or "") or ex["cpf"],
            "email": (d.get("email") or "").strip() or ex["email"],
            "telefone": (d.get("telefone") or "").strip() or ex["telefone"],
            "cidade": (d.get("cidade") or "").strip() or ex["cidade"],
            "estado": (d.get("estado") or "").strip().upper()[:2] or ex["estado"],
            "cep": only_digits(d.get("cep") or "") or ex["cep"],
            "cargo": (d.get("cargo") or "").strip() or ex["cargo"],
            "setor": (d.get("setor") or "").strip() or ex["setor"],
            "vinculo": vinculo or ex["vinculo"],
            "parceiro_id": parceiro_id if parceiro_id is not None else ex["parceiro_id"],
            "ativo": int(d.get("ativo")) if d.get("ativo") is not None else ex["ativo"],
            "foto_url": (d.get("foto_url") or "").strip() or ex["foto_url"],
            "data_admissao": (d.get("data_admissao") or "").strip() or ex["data_admissao"],
            "pis": (d.get("pis") or "").strip() or ex["pis"],
            "ctps_numero": (d.get("ctps_numero") or "").strip() or ex["ctps_numero"],
            "ctps_serie": (d.get("ctps_serie") or "").strip() or ex["ctps_serie"],
            "observacoes": (d.get("observacoes") or "").strip() or ex["observacoes"],
            "usuario_id": usuario_id if usuario_id is not None else ex["usuario_id"],
            "acesso_nivel": acesso_nivel or ex["acesso_nivel"],
        }

        try:
            safe_update(conn, "colaboradores", cid, payload)
            conn.commit()
        except sqlite3.IntegrityError as e:
            return bad_request("Falha ao atualizar colaborador (violação de restrição).", {"detail": str(e)})

        row = conn.execute("SELECT * FROM colaboradores WHERE id=?", (cid,)).fetchone()
        return jsonify(dict(row))

@app.route("/api/colaboradores/<int:id>", methods=["DELETE"])
@login_required
def api_colaboradores_delete(id: int):
    try:
        with get_conn() as conn:
            ex = conn.execute("SELECT id FROM colaboradores WHERE id=?", (id,)).fetchone()
            if not ex:
                return jsonify({"error": "colaborador não encontrado"}), 404
            conn.execute("DELETE FROM colaboradores WHERE id=?", (id,))
            conn.commit()
        return ("", 204)
    except sqlite3.IntegrityError:
        return jsonify({"error": "Não é possível deletar: há registros vinculados."}), 409

# ==========================
# LOGIN / SESSÃO (Páginas)
# ==========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM usuarios WHERE email=? AND ativo=1", (email,)).fetchone()
        if not row or not check_password_hash(row["senha_hash"], password):
            return render_template("login.html", error="Credenciais inválidas."), 401

        session["user_id"] = row["id"]
        session["user_email"] = row["email"]
        session["user_nome"] = row["nome"]
        # row é sqlite3.Row, indexável por chave
        session["user_papel"] = row["papel"] if "papel" in row.keys() else 'admin'
        return redirect(url_for("dashboard_page"))

@app.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/init-admin", methods=["POST"])
def init_admin():
    data = request.get_json(silent=True) or request.form
    nome = (data.get("nome") or "Admin").strip()
    email = (data.get("email") or "").strip().lower()
    senha = data.get("senha") or ""
    if not email or not senha:
        return bad_request("Informe email e senha")
    senha_hash = generate_password_hash(senha)
    with get_conn() as conn:
        ex = conn.execute("SELECT id FROM usuarios WHERE email=?", (email,)).fetchone()
        if ex:
            return jsonify({"ok": True, "msg": "Usuário já existe."})
        conn.execute("""
            INSERT INTO usuarios (nome, email, senha_hash, papel, ativo)
            VALUES (?,?,?,?,1)
        """, (nome, email, senha_hash, "admin"))
    return jsonify({"ok": True})

# ==========================
# PÁGINAS (views HTML)
# ==========================
@app.get("/dashboard", endpoint="dashboard_page")
@login_required
def dashboard_page():
    return render_template("dashboard.html")

# ---- Clientes (lista)
@app.get("/clientes", endpoint="clientes_page")
@app.get("/clientes/page")
@login_required
def clientes_page_view():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM clientes ORDER BY id DESC").fetchall()
    return render_template("clientes.html", clientes=[dict(r) for r in rows])

# ---- Clientes (novo)
@app.route("/clientes/novo", methods=["GET", "POST"], endpoint="client_new_page")
@login_required
def client_new_page():
    if request.method == "GET":
        # Pré-visualização do próximo código (não reservado ainda)
        preview_code = preview_next_client_code()
        return render_template("clientes_form.html", mode="new", cliente=None, preview_code=preview_code)

    # POST (criação)
    razao_social      = (request.form.get("razao_social") or "").strip()
    cnpj_raw          = (request.form.get("cnpj") or "").strip()

    endereco          = (request.form.get("endereco") or "").strip()
    bairro            = (request.form.get("bairro") or "").strip()
    complemento       = (request.form.get("complemento") or "").strip()

    cep_raw           = (request.form.get("cep") or "").strip()
    estado            = (request.form.get("estado") or "").strip().upper()[:2]
    cidade            = (request.form.get("cidade") or "").strip()
    pais              = (request.form.get("pais") or "Brasil").strip()

    # Código interno: sempre gerar no backend para evitar colisões
    codigo_interno_form = (request.form.get("codigo_interno") or "").strip()

    contato_nome      = (request.form.get("contato_nome") or "").strip()
    contato_email     = (request.form.get("contato_email") or "").strip()
    contato_telefone  = (request.form.get("contato_telefone") or "").strip()

    representante     = (request.form.get("representante") or "").strip()
    ncm_padrao        = (request.form.get("ncm_padrao") or "").strip()
    comissao_str      = (request.form.get("comissao_percent") or "").replace(",", ".").strip()
    observacoes       = (request.form.get("observacoes") or "").strip()

    cnpj = only_digits(cnpj_raw)
    cep  = only_digits(cep_raw)
    comissao = float(comissao_str) if comissao_str else 0.0

    if not razao_social or not cnpj:
        err = "Preencha Razão social e CNPJ."
        flash(err, "error")
        return render_template("clientes_form.html", error=err, mode="new", cliente=None)
    if len(cnpj) != 14:
        err = "CNPJ inválido (precisa ter 14 dígitos)."
        flash(err, "error")
        return render_template("clientes_form.html", error=err, mode="new", cliente=None)
    if cep and len(cep) != 8:
        err = "CEP deve ter 8 dígitos (somente números)."
        flash(err, "error")
        return render_template("clientes_form.html", error=err, mode="new", cliente=None)
    if estado and len(estado) != 2:
        err = "Estado (UF) deve ter 2 letras."
        flash(err, "error")
        return render_template("clientes_form.html", error=err, mode="new", cliente=None)

    with get_conn() as conn:
        ex = conn.execute("SELECT id FROM clientes WHERE cnpj=?", (cnpj,)).fetchone()
        if ex:
            err = "CNPJ já cadastrado."
            flash(err, "error")
            preview_code = preview_next_client_code()
            return render_template("clientes_form.html", error=err, mode="new", cliente=None, preview_code=preview_code)

        # Gerar código sequencial dentro da transação. Se admin preencheu manual dentro do padrão e não houver conflito, podemos honrar.
        if current_user_is_admin() and _CLIENT_CODE_REGEX.match(codigo_interno_form or ""):
            # Verificar se já existe
            ex_code = conn.execute("SELECT 1 FROM clientes WHERE codigo_interno=?", (codigo_interno_form,)).fetchone()
            if ex_code:
                codigo_interno = generate_next_client_code(conn)
            else:
                codigo_interno = codigo_interno_form
        else:
            codigo_interno = generate_next_client_code(conn)

        payload = {
            "razao_social": razao_social, "cnpj": cnpj,
            "endereco": endereco, "bairro": bairro, "complemento": complemento,
            "cep": cep, "estado": estado, "cidade": cidade, "pais": pais,
            "codigo_interno": codigo_interno,
            "contato_nome": contato_nome, "contato_email": contato_email, "contato_telefone": contato_telefone,
            "representante": representante, "comissao_percent": comissao, "ncm_padrao": ncm_padrao,
            "observacoes": observacoes,
        }
        safe_insert(conn, "clientes", payload)
        conn.commit()

    flash("Cliente criado com sucesso!", "success")
    return redirect(url_for("clientes_page"))

# ---- Clientes (ver)
@app.get("/clientes/<int:id>", endpoint="clientes_view_page")
@login_required
def clientes_view_page(id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM clientes WHERE id=?", (id,)).fetchone()
        if not row:
            flash("Cliente não encontrado.", "error")
            return redirect(url_for("clientes_page"))
    return render_template("clientes_form.html", mode="view", cliente=dict(row))

# ---- Clientes (editar - GET)
@app.get("/clientes/<int:id>/editar", endpoint="clientes_edit_page")
@login_required
def clientes_edit_page(id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM clientes WHERE id=?", (id,)).fetchone()
        if not row:
            flash("Cliente não encontrado.", "error")
            return redirect(url_for("clientes_page"))
    return render_template("clientes_form.html", mode="edit", cliente=dict(row))

# ---- Clientes (editar - POST)
@app.post("/clientes/<int:id>", endpoint="clientes_update")
@login_required
def clientes_update(id: int):
    # mesmos campos do create
    razao_social      = (request.form.get("razao_social") or "").strip()
    cnpj_raw          = (request.form.get("cnpj") or "").strip()
    endereco          = (request.form.get("endereco") or "").strip()
    bairro            = (request.form.get("bairro") or "").strip()
    complemento       = (request.form.get("complemento") or "").strip()
    cep_raw           = (request.form.get("cep") or "").strip()
    estado            = (request.form.get("estado") or "").strip().upper()[:2]
    cidade            = (request.form.get("cidade") or "").strip()
    pais              = (request.form.get("pais") or "Brasil").strip()
    codigo_interno_form = (request.form.get("codigo_interno") or "").strip()
    contato_nome      = (request.form.get("contato_nome") or "").strip()
    contato_email     = (request.form.get("contato_email") or "").strip()
    contato_telefone  = (request.form.get("contato_telefone") or "").strip()
    representante     = (request.form.get("representante") or "").strip()
    ncm_padrao        = (request.form.get("ncm_padrao") or "").strip()
    comissao_str      = (request.form.get("comissao_percent") or "").replace(",", ".").strip()
    observacoes       = (request.form.get("observacoes") or "").strip()

    cnpj = only_digits(cnpj_raw)
    cep  = only_digits(cep_raw)
    comissao = float(comissao_str) if comissao_str else 0.0

    if not razao_social or not cnpj:
        err = "Preencha Razão social e CNPJ."
        flash(err, "error")
        return render_template("clientes_form.html", error=err, mode="edit", cliente={"id": id})
    if len(cnpj) != 14:
        err = "CNPJ inválido (precisa ter 14 dígitos)."
        flash(err, "error")
        return render_template("clientes_form.html", error=err, mode="edit", cliente={"id": id})
    if cep and len(cep) != 8:
        err = "CEP deve ter 8 dígitos (somente números)."
        flash(err, "error")
        return render_template("clientes_form.html", error=err, mode="edit", cliente={"id": id})
    if estado and len(estado) != 2:
        err = "Estado (UF) deve ter 2 letras."
        flash(err, "error")
        return render_template("clientes_form.html", error=err, mode="edit", cliente={"id": id})

    with get_conn() as conn:
        ex = conn.execute("SELECT id FROM clientes WHERE cnpj=? AND id<>?", (cnpj, id)).fetchone()
        if ex:
            err = "CNPJ já cadastrado em outro cliente."
            flash(err, "error")
            return render_template("clientes_form.html", error=err, mode="edit", cliente={"id": id})

        # Buscar código atual para preservar se usuário não for admin
        cur = conn.execute("SELECT codigo_interno FROM clientes WHERE id=?", (id,)).fetchone()
        current_code = cur["codigo_interno"] if cur else None
        new_code: str = current_code
        if current_user_is_admin() and _CLIENT_CODE_REGEX.match(codigo_interno_form or ""):
            # Permite atualização se não conflitar
            ex_code = conn.execute("SELECT id FROM clientes WHERE codigo_interno=? AND id<>?", (codigo_interno_form, id)).fetchone()
            if not ex_code:
                new_code = codigo_interno_form
        payload = {
            "razao_social": razao_social, "cnpj": cnpj,
            "endereco": endereco, "bairro": bairro, "complemento": complemento,
            "cep": cep, "estado": estado, "cidade": cidade, "pais": pais,
            "codigo_interno": new_code,
            "contato_nome": contato_nome, "contato_email": contato_email, "contato_telefone": contato_telefone,
            "representante": representante, "comissao_percent": comissao, "ncm_padrao": ncm_padrao,
            "observacoes": observacoes,
        }
        safe_update(conn, "clientes", id, payload)
        conn.commit()

    flash("Cliente atualizado com sucesso!", "success")
    return redirect(url_for("clientes_page"))

# (Hardening) Alguns navegadores ou ações podem tentar enviar POST diretamente para /clientes/<id>/editar.
# Para evitar 405 Method Not Allowed se o action do formulário cair nessa URL, aceitamos POST aqui
# e reutilizamos a mesma lógica de atualização.
@app.post("/clientes/<int:id>/editar")
@login_required
def clientes_edit_post_redirect(id: int):
    return clientes_update(id)

# ---- Embalagens (lista)
@app.get("/embalagens", endpoint="embalagens_page")
@app.get("/embalagens/page")
@login_required
def embalagens_page():
    return render_template("embalagens.html")

# ---- Embalagens (novo)
@app.route("/embalagens/novo", methods=["GET", "POST"], endpoint="embalagens_new_page")
@login_required
def embalagens_new_page():
    if request.method == "GET":
        with get_conn() as conn:
            clientes = conn.execute(
                "SELECT id, razao_social FROM clientes ORDER BY razao_social ASC"
            ).fetchall()
        return render_template(
            "embalagens_form.html",
            mode="new",
            embalagem=None,
            clientes=[dict(r) for r in clientes],
        )

    # POST (criação)
    f = request.form
    embalagem_code = (f.get("embalagem_code") or "").strip()
    rev            = (f.get("rev") or "").strip()
    material       = (f.get("material") or "").strip()
    layout_png     = (f.get("layout_png") or "").strip()
    resistencia    = (f.get("resistencia_mecanica") or "").strip()
    observacoes    = (f.get("observacoes") or "").strip()
    ncm_norm       = normalize_ncm(f.get("ncm"))

    def to_int(x):
        try:
            return int(float((x or "").replace(",", ".").strip()))
        except Exception:
            return None

    vendido       = 1 if (f.get("vendido") in ("1","true","True",1,True)) else 0
    cliente_id    = to_int(f.get("cliente_id"))
    espessura_um  = to_int(f.get("espessura_um"))
    largura_mm    = to_int(f.get("largura_mm"))
    altura_mm     = to_int(f.get("altura_mm"))
    sanfona_mm    = to_int(f.get("sanfona_mm"))
    aba_mm        = to_int(f.get("aba_mm"))
    transparencia = to_int(f.get("transparencia"))
    impresso      = 1 if f.get("impresso") else 0
    fita_tipo     = (f.get("fita_tipo") or "").strip()

    if not embalagem_code or not material:
        err = "Preencha Código e Material."
        flash(err, "error")
        with get_conn() as conn:
            clientes = conn.execute(
                "SELECT id, razao_social FROM clientes ORDER BY razao_social ASC"
            ).fetchall()
        return render_template(
            "embalagens_form.html",
            error=err, mode="new", embalagem=None,
            clientes=[dict(r) for r in clientes],
        )
    if vendido and not cliente_id:
        err = "Selecione um Cliente para embalagens marcadas como Vendido."
        flash(err, "error")
        with get_conn() as conn:
            clientes = conn.execute(
                "SELECT id, razao_social FROM clientes ORDER BY razao_social ASC"
            ).fetchall()
        return render_template(
            "embalagens_form.html",
            error=err, mode="new", embalagem=None,
            clientes=[dict(r) for r in clientes],
        )

    with get_conn() as conn:
        # duplicidade código/rev
        ex = conn.execute(
            "SELECT id FROM embalagem_master WHERE embalagem_code=? AND COALESCE(rev,'')=COALESCE(?, '')",
            (embalagem_code, rev or None),
        ).fetchone()
        if ex:
            err = "Já existe uma embalagem com este Código/Rev."
            flash(err, "error")
            clientes = conn.execute(
                "SELECT id, razao_social FROM clientes ORDER BY razao_social ASC"
            ).fetchall()
            return render_template(
                "embalagens_form.html",
                error=err, mode="new", embalagem=None,
                clientes=[dict(r) for r in clientes],
            )

        # valida NCM se informado
        ok, msg = validate_ncm_or_none(conn, ncm_norm)
        if not ok:
            flash(msg, "error")
            clientes = conn.execute(
                "SELECT id, razao_social FROM clientes ORDER BY razao_social ASC"
            ).fetchall()
            return render_template(
                "embalagens_form.html",
                error=msg, mode="new", embalagem=None,
                clientes=[dict(r) for r in clientes],
            )

        payload = {
            "embalagem_code": embalagem_code,
            "rev": rev or None,
            "cliente_id": cliente_id if vendido else None,
            "material": material,
            "espessura_um": espessura_um,
            "largura_mm": largura_mm,
            "altura_mm": altura_mm,
            "sanfona_mm": sanfona_mm,
            "aba_mm": aba_mm,
            "fita_tipo": fita_tipo or "nenhuma",
            "impresso": impresso,
            "layout_png": layout_png or None,
            "transparencia": transparencia,
            "resistencia_mecanica": resistencia,
            "observacoes": observacoes,
            "vendido": vendido,
        }
        if ncm_norm:
            payload["ncm"] = ncm_norm

        safe_insert(conn, "embalagem_master", payload)
        conn.commit()

    flash("Embalagem criada com sucesso!", "success")
    return redirect(url_for("embalagens_page"))



# ---- Embalagens (ver)
@app.get("/embalagens/<int:id>", endpoint="embalagens_view_page")
@login_required
def embalagens_view_page(id: int):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT em.*, c.razao_social AS cliente_nome
            FROM embalagem_master em
            LEFT JOIN clientes c ON c.id = em.cliente_id
            WHERE em.id=?
            """,
            (id,),
        ).fetchone()
        if not row:
            flash("Embalagem não encontrada.", "error")
            return redirect(url_for("embalagens_page"))

        clientes = conn.execute(
            "SELECT id, razao_social FROM clientes ORDER BY razao_social ASC"
        ).fetchall()

    emb = dict(row)
    suggest_ncm = _suggest_ncm_by_material_form(emb.get("material"), emb.get("forma"))

    return render_template(
        "embalagens_form.html",
        mode="view",
        embalagem=emb,
        clientes=[dict(r) for r in clientes],
        suggest_ncm=suggest_ncm,
    )


# ---- Embalagens (editar - GET)
@app.get("/embalagens/<int:id>/editar", endpoint="embalagens_edit_page")
@login_required
def embalagens_edit_page(id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM embalagem_master WHERE id=?", (id,)).fetchone()
        if not row:
            flash("Embalagem não encontrada.", "error")
            return redirect(url_for("embalagens_page"))

        clientes = conn.execute(
            "SELECT id, razao_social FROM clientes ORDER BY razao_social ASC"
        ).fetchall()

    emb = dict(row)
    suggest_ncm = _suggest_ncm_by_material_form(emb.get("material"), emb.get("forma"))

    return render_template(
        "embalagens_form.html",
        mode="edit",
        embalagem=emb,
        clientes=[dict(r) for r in clientes],
        suggest_ncm=suggest_ncm,
    )

@app.post("/embalagens/<int:id>", endpoint="embalagens_update")
@login_required
def embalagens_update(id: int):
    f = request.form
    embalagem_code = (f.get("embalagem_code") or "").strip()
    rev            = (f.get("rev") or "").strip()
    material       = (f.get("material") or "").strip()
    layout_png     = (f.get("layout_png") or "").strip()
    resistencia    = (f.get("resistencia_mecanica") or "").strip()
    observacoes    = (f.get("observacoes") or "").strip()
    ncm_norm       = normalize_ncm(f.get("ncm"))

    def to_int(x):
        try:
            return int(float((x or "").replace(",", ".").strip()))
        except Exception:
            return None

    vendido       = 1 if (f.get("vendido") in ("1","true","True",1,True)) else 0
    cliente_id    = to_int(f.get("cliente_id"))
    espessura_um  = to_int(f.get("espessura_um"))
    largura_mm    = to_int(f.get("largura_mm"))
    altura_mm     = to_int(f.get("altura_mm"))
    sanfona_mm    = to_int(f.get("sanfona_mm"))
    aba_mm        = to_int(f.get("aba_mm"))
    transparencia = to_int(f.get("transparencia"))
    impresso      = 1 if f.get("impresso") else 0
    fita_tipo     = (f.get("fita_tipo") or "").strip() or "nenhuma"

    if not embalagem_code or not material:
        flash("Preencha Código e Material.", "error")
        return redirect(url_for("embalagens_edit_page", id=id))
    if vendido and not cliente_id:
        flash("Selecione um Cliente para embalagens marcadas como Vendido.", "error")
        return redirect(url_for("embalagens_edit_page", id=id))

    with get_conn() as conn:
        # checa duplicidade código/rev em outro id
        ex = conn.execute(
            "SELECT id FROM embalagem_master WHERE embalagem_code=? AND COALESCE(rev,'')=COALESCE(?, '') AND id<>?",
            (embalagem_code, rev or None, id),
        ).fetchone()
        if ex:
            flash("Já existe outra embalagem com este Código/Rev.", "error")
            return redirect(url_for("embalagens_edit_page", id=id))

        # valida NCM se informado
        ok, msg = validate_ncm_or_none(conn, ncm_norm)
        if not ok:
            flash(msg, "error")
            return redirect(url_for("embalagens_edit_page", id=id))

        payload = {
            "embalagem_code": embalagem_code,
            "rev": rev or None,
            "cliente_id": cliente_id if vendido else None,
            "material": material,
            "espessura_um": espessura_um,
            "largura_mm": largura_mm,
            "altura_mm": altura_mm,
            "sanfona_mm": sanfona_mm,
            "aba_mm": aba_mm,
            "fita_tipo": fita_tipo,
            "impresso": impresso,
            "layout_png": layout_png or None,
            "transparencia": transparencia,
            "resistencia_mecanica": resistencia,
            "observacoes": observacoes,
            "vendido": vendido,
        }
        if ncm_norm is not None:
            payload["ncm"] = ncm_norm  # se vazio/inválido não chega aqui

        safe_update(conn, "embalagem_master", id, payload)
        conn.commit()

    flash("Embalagem atualizada com sucesso!", "success")
    return redirect(url_for("embalagens_page"))


# ---- Pedidos (página)
@app.get("/pedidos", endpoint="pedidos_page")
@app.get("/pedidos/page")
@login_required
def pedidos_page():
    return render_template("pedidos.html")

# A rota /pedidos/legacy anteriormente mantinha a versão antiga; agora redireciona para a página unificada
@app.get("/pedidos/legacy", endpoint="pedidos_page_legacy")
@login_required
def pedidos_page_legacy():
    from flask import redirect, url_for
    return redirect(url_for("pedidos_page"))

# ---- Novo Pedido (hub)
@app.get("/pedidos/novo", endpoint="pedido_new_page")
@login_required
def pedido_new_page():
    # Formulário simplificado tornou-se padrão; versões contínuas/complexas removidas
    return render_template("pedidos_form.html")

# ---- Visualizar Pedido (somente leitura)
@app.get("/pedidos/<int:pedido_id>", endpoint="pedido_view_page")
@login_required
def pedido_view_page(pedido_id:int):
    with get_conn() as conn:
        ped = conn.execute("""SELECT p.*, c.razao_social AS cliente_nome
                               FROM pedidos p
                               LEFT JOIN clientes c ON c.id = p.cliente_id
                               WHERE p.id=?""", (pedido_id,)).fetchone()
        if not ped:
            abort(404)
    # Passa o registro para o template; view_mode sinaliza readonly
    return render_template("pedidos_form.html", pedido=dict(ped), view_mode=True)

# ---- Editar Pedido (modo edição — reutiliza mesmo template, sem travar campos)
@app.get("/pedidos/<int:pedido_id>/editar", endpoint="pedido_edit_page")
@login_required
def pedido_edit_page(pedido_id:int):
    with get_conn() as conn:
        ped = conn.execute("SELECT * FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        if not ped:
            abort(404)
    return render_template("pedidos_form.html", pedido=dict(ped), view_mode=False)

# ---- Impressões
@app.get("/impressoes", endpoint="impressoes_page")
@app.get("/impressoes/page")
@login_required
def impressoes_page():
    return render_template("impressoes.html")

# ---- Recebimentos
@app.get("/recebimentos", endpoint="recebimentos_page")
@app.get("/recebimentos/page")
@login_required
def recebimentos_page():
    return render_template("recebimentos.html")

# ---- Corte & Solda
@app.get("/corte-solda", endpoint="corte_solda_page")
@app.get("/corte-solda/page")
@login_required
def corte_solda_page():
    return render_template("corte-solda.html")

# ---- Estoque
@app.get("/estoque", endpoint="estoque_page")
@app.get("/estoque/page")
@login_required
def estoque_page():
    return render_template("estoque.html")

# ---- Expedições
@app.get("/expedicoes", endpoint="expedicoes_page")
@app.get("/expedicoes/page")
@login_required
def expedicoes_page():
    return render_template("expedicoes.html")

# ---- Qualidade
@app.get("/qualidade", endpoint="qualidade_page")
@app.get("/qualidade/page")
@login_required
def qualidade_page():
    return render_template("qualidade.html")

# ---- Relatórios
@app.get("/relatorios", endpoint="relatorios_page")
@app.get("/relatorios/page")
@login_required
def relatorios_page():
    return render_template("relatorios.html")

# ---- Colaboradores (páginas)
@app.get("/colaboradores", endpoint="colaboradores_page")
@app.get("/colaboradores/page")
@login_required
def colaboradores_page():
    # lista básica (se a página fizer fetch via JS, pode só renderizar template vazio)
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM colaboradores ORDER BY nome ASC").fetchall()
    return render_template("colaboradores.html", colaboradores=[dict(r) for r in rows])

@app.route("/colaboradores/novo", methods=["GET", "POST"], endpoint="colaboradores_new_page")
@login_required
def colaboradores_new_page():
    if request.method == "GET":
        with get_conn() as conn:
            # Inclui todos os parceiros; se quiser excluir inativos, tratar visualmente no select
            parceiros = conn.execute("SELECT id, razao_social FROM parceiros ORDER BY razao_social ASC").fetchall()
            usuarios  = conn.execute("SELECT id, nome, email FROM usuarios WHERE ativo=1 ORDER BY nome ASC").fetchall()
        return render_template("colaboradores_form.html", mode="new", colaborador=None,
                               parceiros=[dict(r) for r in parceiros],
                               usuarios=[dict(r) for r in usuarios])

    # POST
    f = request.form
    raw_cpf = only_digits(f.get("cpf") or "")
    payload = {
        "nome": (f.get("nome") or "").strip(),
        "cpf": raw_cpf or None,
        "email": (f.get("email") or "").strip(),
        "telefone": (f.get("telefone") or "").strip(),
        "cidade": (f.get("cidade") or "").strip(),
        "estado": (f.get("estado") or "").strip().upper()[:2],
        "cep": only_digits(f.get("cep") or ""),
        "cargo": (f.get("cargo") or "").strip(),
        "setor": (f.get("setor") or "producao").strip(),
        "vinculo": (f.get("vinculo") or "CLT").strip(),
        "parceiro_id": int(f.get("parceiro_id")) if f.get("parceiro_id") else None,
        "ativo": 1 if f.get("ativo") in ("1","true","True","on") else 1,
        "foto_url": (f.get("foto_url") or "").strip(),
        "data_admissao": (f.get("data_admissao") or "").strip(),
        "pis": (f.get("pis") or "").strip(),
        "ctps_numero": (f.get("ctps_numero") or "").strip(),
        "ctps_serie": (f.get("ctps_serie") or "").strip(),
        "observacoes": (f.get("observacoes") or "").strip(),
        "usuario_id": int(f.get("usuario_id")) if f.get("usuario_id") else None,
        "acesso_nivel": (f.get("acesso_nivel") or "nenhum").strip(),
    }

    # Validações principais (mesmas do REST)
    if not payload["nome"]:
        flash("nome é obrigatório", "error")
        with get_conn() as conn:
            parceiros = conn.execute("SELECT id, razao_social FROM parceiros WHERE ativo=1 ORDER BY razao_social ASC").fetchall()
            usuarios  = conn.execute("SELECT id, nome, email FROM usuarios WHERE ativo=1 ORDER BY nome ASC").fetchall()
        return render_template("colaboradores_form.html", mode="new", colaborador=None,
                               parceiros=[dict(r) for r in parceiros], usuarios=[dict(r) for r in usuarios])

    if payload["vinculo"] == "PJ" and not payload["parceiro_id"]:
        flash("Para vínculo PJ é obrigatório informar o Parceiro.", "error")
        with get_conn() as conn:
            parceiros = conn.execute("SELECT id, razao_social FROM parceiros WHERE ativo=1 ORDER BY razao_social ASC").fetchall()
            usuarios  = conn.execute("SELECT id, nome, email FROM usuarios WHERE ativo=1 ORDER BY nome ASC").fetchall()
        return render_template("colaboradores_form.html", mode="new", colaborador=None,
                               parceiros=[dict(r) for r in parceiros], usuarios=[dict(r) for r in usuarios])

    if payload["acesso_nivel"] != "nenhum" and not payload["usuario_id"]:
        flash("Para conceder acesso ao sistema selecione um Usuário.", "error")
        with get_conn() as conn:
            parceiros = conn.execute("SELECT id, razao_social FROM parceiros WHERE ativo=1 ORDER BY razao_social ASC").fetchall()
            usuarios  = conn.execute("SELECT id, nome, email FROM usuarios WHERE ativo=1 ORDER BY nome ASC").fetchall()
        return render_template("colaboradores_form.html", mode="new", colaborador=None,
                               parceiros=[dict(r) for r in parceiros], usuarios=[dict(r) for r in usuarios])

    with get_conn() as conn:
        try:
            cid = safe_insert(conn, "colaboradores", payload)
            conn.commit()
        except sqlite3.IntegrityError as e:
            msg = str(e)
            if "cpf" in msg.lower():
                flash("CPF já cadastrado para outro colaborador.", "error")
            else:
                flash("Falha ao criar colaborador (restrição/único).", "error")
            parceiros = conn.execute("SELECT id, razao_social FROM parceiros WHERE ativo=1 ORDER BY razao_social ASC").fetchall()
            usuarios  = conn.execute("SELECT id, nome, email FROM usuarios WHERE ativo=1 ORDER BY nome ASC").fetchall()
            return render_template("colaboradores_form.html", mode="new", colaborador=None,
                                   parceiros=[dict(r) for r in parceiros], usuarios=[dict(r) for r in usuarios])

    flash("Colaborador criado com sucesso!", "success")
    return redirect(url_for("colaboradores_page"))

@app.get("/colaboradores/<int:id>", endpoint="colaboradores_view_page")
@login_required
def colaboradores_view_page(id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM colaboradores WHERE id=?", (id,)).fetchone()
        if not row:
            flash("Colaborador não encontrado.", "error")
            return redirect(url_for("colaboradores_page"))
    return render_template("colaboradores_form.html", mode="view", colaborador=dict(row))

@app.get("/colaboradores/<int:id>/editar", endpoint="colaboradores_edit_page")
@login_required
def colaboradores_edit_page(id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM colaboradores WHERE id=?", (id,)).fetchone()
        if not row:
            flash("Colaborador não encontrado.", "error")
            return redirect(url_for("colaboradores_page"))
        parceiros = conn.execute("SELECT id, razao_social FROM parceiros ORDER BY razao_social ASC").fetchall()
        usuarios  = conn.execute("SELECT id, nome, email FROM usuarios WHERE ativo=1 ORDER BY nome ASC").fetchall()
    return render_template("colaboradores_form.html", mode="edit", colaborador=dict(row),
                           parceiros=[dict(r) for r in parceiros],
                           usuarios=[dict(r) for r in usuarios])

@app.post("/colaboradores/<int:id>", endpoint="colaboradores_update")
@login_required
def colaboradores_update(id: int):
    f = request.form
    raw_cpf = only_digits(f.get("cpf") or "")
    payload = {
        "nome": (f.get("nome") or "").strip(),
        "cpf": raw_cpf or None,
        "email": (f.get("email") or "").strip(),
        "telefone": (f.get("telefone") or "").strip(),
        "cidade": (f.get("cidade") or "").strip(),
        "estado": (f.get("estado") or "").strip().upper()[:2],
        "cep": only_digits(f.get("cep") or ""),
        "cargo": (f.get("cargo") or "").strip(),
        "setor": (f.get("setor") or "").strip(),
        "vinculo": (f.get("vinculo") or "").strip(),
        "parceiro_id": int(f.get("parceiro_id")) if f.get("parceiro_id") else None,
        "ativo": 1 if f.get("ativo") in ("1","true","True","on") else 0,
        "foto_url": (f.get("foto_url") or "").strip(),
        "data_admissao": (f.get("data_admissao") or "").strip(),
        "pis": (f.get("pis") or "").strip(),
        "ctps_numero": (f.get("ctps_numero") or "").strip(),
        "ctps_serie": (f.get("ctps_serie") or "").strip(),
        "observacoes": (f.get("observacoes") or "").strip(),
        "usuario_id": int(f.get("usuario_id")) if f.get("usuario_id") else None,
        "acesso_nivel": (f.get("acesso_nivel") or "").strip(),
    }

    # Regras
    if payload["vinculo"] == "PJ" and not payload["parceiro_id"]:
        flash("Para vínculo PJ é obrigatório informar o Parceiro.", "error")
        with get_conn() as conn:
            parceiros = conn.execute("SELECT id, razao_social FROM parceiros WHERE ativo=1 ORDER BY razao_social ASC").fetchall()
            usuarios  = conn.execute("SELECT id, nome, email FROM usuarios WHERE ativo=1 ORDER BY nome ASC").fetchall()
        return render_template("colaboradores_form.html", mode="edit", colaborador={"id": id, **payload},
                               parceiros=[dict(r) for r in parceiros], usuarios=[dict(r) for r in usuarios])

    if payload["acesso_nivel"] and payload["acesso_nivel"] != "nenhum" and not payload["usuario_id"]:
        flash("Para conceder acesso ao sistema selecione um Usuário.", "error")
        with get_conn() as conn:
            parceiros = conn.execute("SELECT id, razao_social FROM parceiros WHERE ativo=1 ORDER BY razao_social ASC").fetchall()
            usuarios  = conn.execute("SELECT id, nome, email FROM usuarios WHERE ativo=1 ORDER BY nome ASC").fetchall()
        return render_template("colaboradores_form.html", mode="edit", colaborador={"id": id, **payload},
                               parceiros=[dict(r) for r in parceiros], usuarios=[dict(r) for r in usuarios])

    with get_conn() as conn:
        try:
            safe_update(conn, "colaboradores", id, payload)
            conn.commit()
        except sqlite3.IntegrityError as e:
            msg = str(e)
            if "cpf" in msg.lower():
                flash("CPF já cadastrado para outro colaborador.", "error")
            else:
                flash("Falha ao atualizar colaborador (restrição/único).", "error")
            parceiros = conn.execute("SELECT id, razao_social FROM parceiros WHERE ativo=1 ORDER BY razao_social ASC").fetchall()
            usuarios  = conn.execute("SELECT id, nome, email FROM usuarios WHERE ativo=1 ORDER BY nome ASC").fetchall()
            return render_template("colaboradores_form.html", mode="edit", colaborador={"id": id, **payload},
                                   parceiros=[dict(r) for r in parceiros], usuarios=[dict(r) for r in usuarios])

    flash("Colaborador atualizado com sucesso!", "success")
    return redirect(url_for("colaboradores_page"))

# ==========================
# PARCEIROS (REST + Páginas)
# ==========================
@app.route("/api/parceiros", methods=["GET"])
def api_parceiros_list():
    ativo = request.args.get("ativo")
    tipo = request.args.get("tipo")
    q = request.args.get("q")

    sql = "SELECT * FROM parceiros WHERE 1=1"
    params = []
    if ativo is not None:
        sql += " AND ativo=?"
        params.append(int(ativo))
    if tipo:
        sql += " AND tipo=?"
        params.append(tipo)
    if q:
        sql += " AND (razao_social LIKE ? OR cnpj LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like])
    sql += " ORDER BY razao_social ASC"

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        data = []
        for r in rows:
            d = dict(r)
            d["contato"] = _compose_contato(d)  # compat com frontend antigo
            data.append(d)
        return jsonify(data)

@app.route("/api/parceiros", methods=["POST"])
def api_parceiros_create():
    d = request.json or {}
    razao_social = (d.get("razao_social") or "").strip()
    cnpj = only_digits(d.get("cnpj") or "")
    cep  = only_digits(d.get("cep") or "")
    estado = (d.get("estado") or "").strip().upper()[:2]

    if not razao_social or not cnpj:
        return bad_request("Preencha Razão social e CNPJ.")
    if len(cnpj) != 14:
        return bad_request("CNPJ inválido (precisa ter 14 dígitos).")
    if cep and len(cep) != 8:
        return bad_request("CEP deve ter 8 dígitos (somente números).")
    if estado and len(estado) != 2:
        return bad_request("Estado (UF) deve ter 2 letras.")

    with get_conn() as conn:
        ex = conn.execute("SELECT id FROM parceiros WHERE cnpj=?", (cnpj,)).fetchone()
        if ex:
            return bad_request("CNPJ já cadastrado.", {"parceiro_id": ex["id"]})

        codigo_interno = (d.get("codigo_interno") or "").strip()
        if not _PARTNER_CODE_REGEX.match(codigo_interno):
            # gera automaticamente
            codigo_interno = generate_next_partner_code(conn)

        payload = {
            "razao_social": razao_social,
            "cnpj": cnpj,  # obrigatório
            "tipo": (d.get("tipo") or "fornecedor").strip(),
            "endereco": (d.get("endereco") or "").strip(),
            "bairro": (d.get("bairro") or "").strip(),
            "complemento": (d.get("complemento") or "").strip(),
            "cep": cep or None,
            "estado": estado or None,
            "cidade": (d.get("cidade") or "").strip(),
            "pais": (d.get("pais") or "Brasil").strip(),
            "contato_nome": (d.get("contato_nome") or "").strip(),
            "contato_email": (d.get("contato_email") or "").strip(),
            "contato_telefone": (d.get("contato_telefone") or "").strip(),
            "representante": (d.get("representante") or "").strip(),
            "email": (d.get("email") or "").strip(),
            "telefone": (d.get("telefone") or "").strip(),
            "observacoes": (d.get("observacoes") or "").strip(),
            "ativo": int(d.get("ativo")) if d.get("ativo") is not None else 1,
            "servicos_json": (d.get("servicos_json") or "[]").strip(),
            "codigo_interno": codigo_interno,
        }
        pid = safe_insert(conn, "parceiros", payload)
        row = conn.execute("SELECT * FROM parceiros WHERE id=?", (pid,)).fetchone()
        return jsonify(dict(row)), 201

# ---- DELETE parceiro
@app.route("/api/parceiros/<int:id>", methods=["DELETE"])
@login_required
def api_parceiros_delete(id: int):
    try:
        with get_conn() as conn:
            ex = conn.execute("SELECT id FROM parceiros WHERE id=?", (id,)).fetchone()
            if not ex:
                return jsonify({"error": "parceiro não encontrado"}), 404
            conn.execute("DELETE FROM parceiros WHERE id=?", (id,))
            conn.commit()
        return ("", 204)
    except sqlite3.IntegrityError:
        return jsonify({"error": "Não é possível deletar: há registros vinculados."}), 409

# ---- Parceiros (páginas)
@app.get("/parceiros", endpoint="parceiros_page")
@app.get("/parceiros/page")
@login_required
def parceiros_page():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM parceiros ORDER BY razao_social ASC, id DESC").fetchall()
    # adiciona campo calculado contato p/ compat
    parceiros = []
    for r in rows:
        d = dict(r)
        d["contato"] = _compose_contato(d)
        parceiros.append(d)
    return render_template("parceiros.html", parceiros=parceiros)

@app.route("/parceiros/novo", methods=["GET", "POST"], endpoint="parceiros_new_page")
@login_required
def parceiros_new_page():
    if request.method == "GET":
        return render_template("parceiros_form.html", mode="new", parceiro=None)

    f = request.form
    razao_social = (f.get("razao_social") or "").strip()
    cnpj_raw     = (f.get("cnpj") or "").strip()
    tipo         = (f.get("tipo") or "fornecedor").strip()
    endereco     = (f.get("endereco") or "").strip()
    bairro       = (f.get("bairro") or "").strip()
    complemento  = (f.get("complemento") or "").strip()
    cep_raw      = (f.get("cep") or "").strip()
    estado       = (f.get("estado") or "").strip().upper()[:2]
    cidade       = (f.get("cidade") or "").strip()
    pais         = (f.get("pais") or "Brasil").strip()

    # aceita tanto campos novos quanto "contato" antigo para nome
    contato_nome      = (f.get("contato_nome") or f.get("contato") or "").strip()
    contato_email     = (f.get("contato_email") or "").strip()
    contato_telefone  = (f.get("contato_telefone") or "").strip()

    representante= (f.get("representante") or "").strip()
    email        = (f.get("email") or "").strip()
    telefone     = (f.get("telefone") or "").strip()
    observacoes  = (f.get("observacoes") or "").strip()
    ativo        = 1 if (f.get("ativo") in ("1","true","True","on")) else 0
    servicos_json= (f.get("servicos_json") or "[]").strip()

    cnpj = only_digits(cnpj_raw)
    cep  = only_digits(cep_raw)

    if not razao_social or not cnpj:
        err = "Preencha a Razão social e o CNPJ."
        flash(err, "error")
        return render_template("parceiros_form.html", error=err, mode="new", parceiro=None)
    if len(cnpj) != 14:
        err = "CNPJ inválido (precisa ter 14 dígitos)."
        flash(err, "error")
        return render_template("parceiros_form.html", error=err, mode="new", parceiro=None)
    if cep and len(cep) != 8:
        err = "CEP deve ter 8 dígitos (somente números)."
        flash(err, "error")
        return render_template("parceiros_form.html", error=err, mode="new", parceiro=None)
    if estado and len(estado) != 2:
        err = "Estado (UF) deve ter 2 letras."
        flash(err, "error")
        return render_template("parceiros_form.html", error=err, mode="new", parceiro=None)

    with get_conn() as conn:
        ex = conn.execute("SELECT id FROM parceiros WHERE cnpj=?", (cnpj,)).fetchone()
        if ex:
            err = "CNPJ já cadastrado."
            flash(err, "error")
            return render_template("parceiros_form.html", error=err, mode="new", parceiro=None)

        codigo_interno = (f.get("codigo_interno") or "").strip()
        if not _PARTNER_CODE_REGEX.match(codigo_interno):
            codigo_interno = generate_next_partner_code(conn)

        payload = {
            "razao_social": razao_social,
            "cnpj": cnpj,  # obrigatório
            "tipo": tipo,
            "endereco": endereco,
            "bairro": bairro,
            "complemento": complemento,
            "cep": cep or None,
            "estado": estado or None,
            "cidade": cidade,
            "pais": pais,
            "contato_nome": contato_nome,
            "contato_email": contato_email,
            "contato_telefone": contato_telefone,
            "representante": representante,
            "email": email,
            "telefone": telefone,
            "observacoes": observacoes,
            "ativo": ativo,
            "servicos_json": servicos_json,
            "codigo_interno": codigo_interno,
        }
        safe_insert(conn, "parceiros", payload)
        conn.commit()

    flash("Parceiro criado com sucesso!", "success")
    return redirect(url_for("parceiros_page"))

@app.get("/parceiros/<int:id>", endpoint="parceiros_view_page")
@login_required
def parceiros_view_page(id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM parceiros WHERE id=?", (id,)).fetchone()
        if not row:
            flash("Parceiro não encontrado.", "error")
            return redirect(url_for("parceiros_page"))
        d = dict(row)
        d["contato"] = _compose_contato(d)  # compat com template
    return render_template("parceiros_form.html", mode="view", parceiro=d)

@app.get("/parceiros/<int:id>/editar", endpoint="parceiros_edit_page")
@login_required
def parceiros_edit_page(id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM parceiros WHERE id=?", (id,)).fetchone()
        if not row:
            flash("Parceiro não encontrado.", "error")
            return redirect(url_for("parceiros_page"))
        d = dict(row)
        d["contato"] = _compose_contato(d)  # compat se o form ainda mostrar 1 campo
    return render_template("parceiros_form.html", mode="edit", parceiro=d)

@app.post("/parceiros/<int:id>", endpoint="parceiros_update")
@login_required
def parceiros_update(id: int):
    f = request.form
    razao_social = (f.get("razao_social") or "").strip()
    cnpj_raw     = (f.get("cnpj") or "").strip()
    tipo         = (f.get("tipo") or "fornecedor").strip()
    endereco     = (f.get("endereco") or "").strip()
    bairro       = (f.get("bairro") or "").strip()
    complemento  = (f.get("complemento") or "").strip()
    cep_raw      = (f.get("cep") or "").strip()
    estado       = (f.get("estado") or "").strip().upper()[:2]
    cidade       = (f.get("cidade") or "").strip()
    pais         = (f.get("pais") or "Brasil").strip()

    contato_nome      = (f.get("contato_nome") or f.get("contato") or "").strip()
    contato_email     = (f.get("contato_email") or "").strip()
    contato_telefone  = (f.get("contato_telefone") or "").strip()

    representante= (f.get("representante") or "").strip()
    email        = (f.get("email") or "").strip()
    telefone     = (f.get("telefone") or "").strip()
    observacoes  = (f.get("observacoes") or "").strip()
    ativo        = 1 if (f.get("ativo") in ("1","true","True","on")) else 0
    servicos_json= (f.get("servicos_json") or "[]").strip()

    cnpj = only_digits(cnpj_raw)
    cep  = only_digits(cep_raw)

    if not razao_social or not cnpj:
        err = "Preencha a Razão social e o CNPJ."
        flash(err, "error")
        return render_template("parceiros_form.html", error=err, mode="edit", parceiro={"id": id})
    if len(cnpj) != 14:
        err = "CNPJ inválido (precisa ter 14 dígitos)."
        flash(err, "error")
        return render_template("parceiros_form.html", error=err, mode="edit", parceiro={"id": id})
    if cep and len(cep) != 8:
        err = "CEP deve ter 8 dígitos (somente números)."
        flash(err, "error")
        return render_template("parceiros_form.html", error=err, mode="edit", parceiro={"id": id})
    if estado and len(estado) != 2:
        err = "Estado (UF) deve ter 2 letras."
        flash(err, "error")
        return render_template("parceiros_form.html", error=err, mode="edit", parceiro={"id": id})

    with get_conn() as conn:
        ex = conn.execute("SELECT id FROM parceiros WHERE cnpj=? AND id<>?", (cnpj, id)).fetchone()
        if ex:
            err = "CNPJ já cadastrado em outro parceiro."
            flash(err, "error")
            return render_template("parceiros_form.html", error=err, mode="edit", parceiro={"id": id})

        payload = {
            "razao_social": razao_social,
            "cnpj": cnpj,
            "tipo": tipo,
            "endereco": endereco,
            "bairro": bairro,
            "complemento": complemento,
            "cep": cep or None,
            "estado": estado or None,
            "cidade": cidade,
            "pais": pais,
            "contato_nome": contato_nome,
            "contato_email": contato_email,
            "contato_telefone": contato_telefone,
            "representante": representante,
            "email": email,
            "telefone": telefone,
            "observacoes": observacoes,
            "ativo": ativo,
            "servicos_json": servicos_json,
        }
        safe_update(conn, "parceiros", id, payload)
        conn.commit()

    flash("Parceiro atualizado com sucesso!", "success")
    return redirect(url_for("parceiros_page"))

# (opcional) rota de diagnóstico
@app.get("/__routes__")
def __routes__():
    linhas = []
    for r in sorted(app.url_map.iter_rules(), key=lambda x: x.rule):
        linhas.append(f"{r.endpoint:25s}  {','.join(sorted(r.methods - {'HEAD','OPTIONS'})) or '-':10s}  {r.rule}")
    return "<pre>" + "\n".join(linhas) + "</pre>"

@app.get("/__dbdiag__")
def __dbdiag__():
    with get_conn() as conn:
        tabs = [r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    return jsonify({"db_path": DB_PATH, "tables": tabs})

# ==========================
# MAIN
# ==========================
if __name__ == "__main__":
    app.run(debug=True)
