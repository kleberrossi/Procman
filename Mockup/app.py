# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
import re
from functools import wraps
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from db import get_conn, init_db, DB_PATH, bootstrap_db
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

def bad_request(msg: str, extra: dict | None = None):
    payload = {"error": msg}
    if extra:
        payload.update(extra)
    return jsonify(payload), 400

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
    with get_conn() as conn:
        cur = conn.execute("""
          INSERT INTO embalagem_master(
            embalagem_code, rev, cliente_id, material, espessura_um, largura_mm, altura_mm,
            sanfona_mm, aba_mm, fita_tipo, impresso, layout_png, transparencia, resistencia_mecanica
          ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data["embalagem_code"], data.get("rev", "R00"), data.get("cliente_id"),
            data["material"], data.get("espessura_um"), data.get("largura_mm"), data.get("altura_mm"),
            data.get("sanfona_mm", 0), data.get("aba_mm", 0), data.get("fita_tipo", "nenhuma"),
            1 if data.get("impresso") else 0, data.get("layout_png"),
            data.get("transparencia"), data.get("resistencia_mecanica")
        ))
        eid = cur.lastrowid
        row = conn.execute("SELECT * FROM embalagem_master WHERE id=?", (eid,)).fetchone()
        return jsonify(dict(row)), 201

# ==========================
# PEDIDOS (REST)
# ==========================
@app.route("/api/pedidos", methods=["GET"])
def api_pedidos_list():
    with get_conn() as conn:
        rows = conn.execute("""
          SELECT p.*, c.razao_social AS cliente_nome
          FROM pedidos p
          LEFT JOIN clientes c ON c.id = p.cliente_id
          ORDER BY p.id DESC
        """).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route("/api/pedidos", methods=["POST"])
def api_pedidos_create():
    data = request.json or {}
    with get_conn() as conn:
        cur = conn.execute("""
          INSERT INTO pedidos(cliente_id, numero_pedido, data_emissao, data_prevista,
                              quantidade_tipo, status, preco_total, margem_toler_percent, ncm)
          VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            data["cliente_id"], data["numero_pedido"], data["data_emissao"], data.get("data_prevista"),
            data["quantidade_tipo"], data.get("status", "RASCUNHO"), data.get("preco_total"),
            data.get("margem_toler_percent", 0), data.get("ncm")
        ))
        pid = cur.lastrowid
        row = conn.execute("SELECT * FROM pedidos WHERE id=?", (pid,)).fetchone()
        return jsonify(dict(row)), 201

@app.route("/api/pedidos/<int:pedido_id>", methods=["GET"])
def api_pedidos_detail(pedido_id):
    with get_conn() as conn:
        pedido = conn.execute("SELECT * FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        if not pedido:
            return jsonify({"error": "pedido não encontrado"}), 404
        itens = conn.execute("SELECT * FROM pedido_itens WHERE pedido_id=?", (pedido_id,)).fetchall()
        return jsonify({"pedido": dict(pedido), "itens": [dict(i) for i in itens]})

@app.route("/api/pedidos/<int:pedido_id>/itens", methods=["POST"])
def api_pedido_itens_add(pedido_id):
    data = request.json or {}
    with get_conn() as conn:
        ped = conn.execute("SELECT * FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
        if not ped:
            return jsonify({"error": "pedido não encontrado"}), 404
        cur = conn.execute("""
          INSERT INTO pedido_itens(pedido_id, embalagem_code, rev, descricao, qtd, preco_unit, margem_toler_percent)
          VALUES (?,?,?,?,?,?,?)
        """, (
            pedido_id, data["embalagem_code"], data["rev"], data.get("descricao"),
            data["qtd"], data.get("preco_unit"), data.get("margem_toler_percent")
        ))
        iid = cur.lastrowid
        row = conn.execute("SELECT * FROM pedido_itens WHERE id=?", (iid,)).fetchone()
        return jsonify(dict(row)), 201

# ==========================
# CÁLCULOS (REST)
# ==========================
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
# FUNÇÕES & FUNCIONÁRIOS (REST)
# ==========================
# ---- Funções
@app.route("/api/funcoes", methods=["GET"])
def api_funcoes_list():
    ativo = request.args.get("ativo")
    area = request.args.get("area")
    q = request.args.get("q")

    sql = "SELECT * FROM funcoes WHERE 1=1"
    params = []
    if ativo is not None:
        sql += " AND ativo=?"
        params.append(int(ativo))
    if area:
        sql += " AND area=?"
        params.append(area)
    if q:
        sql += " AND nome LIKE ?"
        params.append(f"%{q}%")
    sql += " ORDER BY nome ASC"

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route("/api/funcoes", methods=["POST"])
def api_funcoes_create():
    d = request.json or {}
    if not d.get("nome"):
        return bad_request("nome é obrigatório")
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO funcoes (nome, area, nivel, descricao, ativo)
            VALUES (?,?,?,?, COALESCE(?,1))
        """, (d["nome"], d.get("area", "producao"), d.get("nivel"), d.get("descricao"), d.get("ativo")))
        fid = cur.lastrowid
        row = conn.execute("SELECT * FROM funcoes WHERE id=?", (fid,)).fetchone()
        return jsonify(dict(row)), 201

# ---- Funcionários / Colaboradores
@app.route("/api/funcionarios", methods=["GET"])
@app.route("/api/colaboradores", methods=["GET"])
def api_funcionarios_list():
    ativo = request.args.get("ativo")
    setor = request.args.get("setor")
    funcao_id = request.args.get("funcao_id")
    q = request.args.get("q")

    sql = """
      SELECT f.*, fu.nome AS funcao_nome
      FROM funcionarios f
      LEFT JOIN funcoes fu ON fu.id = f.funcao_id
      WHERE 1=1
    """
    params = []
    if ativo is not None:
        sql += " AND f.ativo=?"
        params.append(int(ativo))
    if setor:
        sql += " AND f.setor=?"
        params.append(setor)
    if funcao_id:
        sql += " AND f.funcao_id=?"
        params.append(int(funcao_id))
    if q:
        sql += " AND (f.nome LIKE ? OR f.matricula LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])
    sql += " ORDER BY f.nome ASC"

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route("/api/funcionarios", methods=["POST"])
@app.route("/api/colaboradores", methods=["POST"])
def api_funcionarios_create():
    d = request.json or {}
    if not d.get("nome"):
        return bad_request("nome é obrigatório")

    with get_conn() as conn:
        cur = conn.execute("""
          INSERT INTO funcionarios (
            nome, cpf, matricula, email, telefone, setor, funcao_id,
            data_nascimento, data_admissao, data_inicio_funcao, ativo, observacoes
          ) VALUES (?,?,?,?,?,?,?,?,?,?, COALESCE(?,1), ?)
        """, (
            d["nome"], d.get("cpf"), d.get("matricula"), d.get("email"), d.get("telefone"),
            d.get("setor", "producao"), d.get("funcao_id"),
            d.get("data_nascimento"), d.get("data_admissao"), d.get("data_inicio_funcao"),
            d.get("ativo"), d.get("observacoes")
        ))
        rid = cur.lastrowid
        row = conn.execute("""
            SELECT f.*, fu.nome AS funcao_nome
            FROM funcionarios f
            LEFT JOIN funcoes fu ON fu.id = f.funcao_id
            WHERE f.id=?
        """, (rid,)).fetchone()
        return jsonify(dict(row)), 201

# ==========================
# PARCEIROS (REST)
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
        return render_template("clientes_form.html", mode="new", cliente=None)

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

    codigo_interno    = (request.form.get("codigo_interno") or "").strip()

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
            return render_template("clientes_form.html", error=err, mode="new", cliente=None)

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
    codigo_interno    = (request.form.get("codigo_interno") or "").strip()
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

        payload = {
            "razao_social": razao_social, "cnpj": cnpj,
            "endereco": endereco, "bairro": bairro, "complemento": complemento,
            "cep": cep, "estado": estado, "cidade": cidade, "pais": pais,
            "codigo_interno": codigo_interno,
            "contato_nome": contato_nome, "contato_email": contato_email, "contato_telefone": contato_telefone,
            "representante": representante, "comissao_percent": comissao, "ncm_padrao": ncm_padrao,
            "observacoes": observacoes,
        }
        safe_update(conn, "clientes", id, payload)
        conn.commit()

    flash("Cliente atualizado com sucesso!", "success")
    return redirect(url_for("clientes_page"))

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

    def to_int(x):
        try:
            return int(float((x or "").replace(",", ".").strip()))
        except Exception:
            return None

    cliente_id    = to_int(f.get("cliente_id"))
    espessura_um  = to_int(f.get("espessura_um"))
    largura_mm    = to_int(f.get("largura_mm"))
    altura_mm     = to_int(f.get("altura_mm"))
    sanfona_mm    = to_int(f.get("sanfona_mm"))
    aba_mm        = to_int(f.get("aba_mm"))
    transparencia = to_int(f.get("transparencia"))
    impresso      = 1 if f.get("impresso") else 0
    fita_tipo     = (f.get("fita_tipo") or "").strip()

    if not embalagem_code or not cliente_id or not material:
        err = "Preencha Código, Cliente e Material."
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

        payload = {
            "embalagem_code": embalagem_code,
            "rev": rev or None,
            "cliente_id": cliente_id,
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
        }
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

    return render_template(
        "embalagens_form.html",
        mode="view",
        embalagem=dict(row),
        clientes=[dict(r) for r in clientes],
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

    return render_template(
        "embalagens_form.html",
        mode="edit",
        embalagem=dict(row),
        clientes=[dict(r) for r in clientes],
    )

# ---- Embalagens (editar - POST)
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

    def to_int(x):
        try:
            return int(float((x or "").replace(",", ".").strip()))
        except Exception:
            return None

    cliente_id    = to_int(f.get("cliente_id"))
    espessura_um  = to_int(f.get("espessura_um"))
    largura_mm    = to_int(f.get("largura_mm"))
    altura_mm     = to_int(f.get("altura_mm"))
    sanfona_mm    = to_int(f.get("sanfona_mm"))
    aba_mm        = to_int(f.get("aba_mm"))
    transparencia = to_int(f.get("transparencia"))
    impresso      = 1 if f.get("impresso") else 0
    fita_tipo     = (f.get("fita_tipo") or "").strip()

    if not embalagem_code or not cliente_id or not material:
        err = "Preencha Código, Cliente e Material."
        flash(err, "error")
        return redirect(url_for("embalagens_edit_page", id=id))

    with get_conn() as conn:
        ex = conn.execute(
            "SELECT id FROM embalagem_master WHERE embalagem_code=? AND COALESCE(rev,'')=COALESCE(?, '') AND id<>?",
            (embalagem_code, rev or None, id),
        ).fetchone()
        if ex:
            err = "Já existe outra embalagem com este Código/Rev."
            flash(err, "error")
            return redirect(url_for("embalagens_edit_page", id=id))

        payload = {
            "embalagem_code": embalagem_code,
            "rev": rev or None,
            "cliente_id": cliente_id,
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
        }
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

# ---- Funcionários
@app.get("/funcionarios", endpoint="funcionarios_page")
@app.get("/funcionarios/page")
@login_required
def funcionarios_page():
    with get_conn() as conn:
        funcs = conn.execute("""
            SELECT f.*, fu.nome AS funcao_nome
            FROM funcionarios f
            LEFT JOIN funcoes fu ON fu.id = f.funcao_id
            ORDER BY f.nome ASC
        """).fetchall()
        funcoes = conn.execute("""
            SELECT * FROM funcoes WHERE ativo=1 ORDER BY nome ASC
        """).fetchall()
    return render_template("funcionarios.html",
                           funcionarios=[dict(r) for r in funcs],
                           funcoes=[dict(r) for r in funcoes])

# ---- Colaboradores (alias)
@app.get("/colaboradores", endpoint="colaboradores_page")
@app.get("/colaboradores/page")
@login_required
def colaboradores_page():
    return redirect(url_for("funcionarios_page"))

# ---- Parceiros (lista)
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

# ---- Parceiros (novo)
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
        }
        safe_insert(conn, "parceiros", payload)
        conn.commit()

    flash("Parceiro criado com sucesso!", "success")
    return redirect(url_for("parceiros_page"))

# ---- Parceiros (ver)
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

# ---- Parceiros (editar - GET)
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

# ---- Parceiros (editar - POST)
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
