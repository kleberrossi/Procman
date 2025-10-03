"""db.py

Camada de inicialização e migrações aditivas do SQLite.

Notas de padronização relevantes (set 2025):
1. Códigos internos sequenciais
    - Clientes  : C00000..C99999 (campo clientes.codigo_interno)
    - Parceiros : P00000..P99999 (campo parceiros.codigo_interno)
    A geração ocorre SEM reservas de gaps: ao inserir, buscamos o maior sufixo
    válido e incrementamos dentro da mesma transação. Índices UNIQUE protegem
    contra duplicidade (idxu_clientes_codigo / idxu_parceiros_codigo). Em bancos
    legados o bootstrap faz backfill automático seguindo a ordem crescente de id.

2. Migrações aditivas
    - Somente ALTER TABLE ADD COLUMN, criação de índices e views. Não fazemos
      re‑escrita de tabela (mais cara) para não bloquear a subida. Restrições
      NOT NULL/DEFAULT presentes em schema.sql podem estar ausentes aqui; o
      backend valida regras de negócio antes de persistir.

3. Embalagem Master (embalagem_master)
    - Inclui coluna opcional ncm (8 dígitos) com CHECK simples. Se ausente em
      banco legado, bootstrap adiciona (ADD COLUMN). O app só grava se validar.

Manter esta seção curta e factual; detalhes extensos podem ir para README.
"""
# db.py
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("APP_DB_PATH", "app.db")

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Boas práticas no SQLite
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------- helpers de migração aditiva ----------
def _table_cols(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]

def _add_col_if_missing(conn: sqlite3.Connection, table: str, col_def: str):
    col_name = col_def.strip().split()[0]
    if col_name not in _table_cols(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")

def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone())

def _view_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name=?", (name,)
    ).fetchone())


# ---------- criação “do zero” (idempotente) ----------
def init_db():
    with get_conn() as conn:
        # =========================
        # USUÁRIOS / AUTENTICAÇÃO
        # =========================
        conn.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            nome         TEXT,
            email        TEXT,
            senha_hash   TEXT,
            papel        TEXT,
            ativo        INTEGER DEFAULT 1,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idxu_usuarios_email ON usuarios(email);")

        # =========================
        # NUMERADORES (sequências globais)
        # =========================
        # Armazena último sufixo numérico gerado para códigos sequenciais.
        # Ex: ('PED', 42) -> próximo será PED-000043
        conn.execute("""
        CREATE TABLE IF NOT EXISTS numeradores (
            nome   TEXT PRIMARY KEY,
            ultimo INTEGER NOT NULL
        );
        """)

        # =========================
        # CLIENTES
        # =========================
        conn.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            razao_social      TEXT NOT NULL,
            cnpj              TEXT NOT NULL,
            endereco          TEXT,
            bairro            TEXT,
            complemento       TEXT,
            cep               TEXT,
            estado            TEXT,
            cidade            TEXT,
            pais              TEXT DEFAULT 'Brasil',
            codigo_interno    TEXT,
            contato_nome      TEXT,
            contato_email     TEXT,
            contato_telefone  TEXT,
            representante     TEXT,
            comissao_percent  REAL,
            ncm_padrao        TEXT,
            observacoes       TEXT,
            created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_clientes_cnpj ON clientes(cnpj);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_clientes_razao ON clientes(razao_social);")

        # =========================
        # EMBALAGEM MASTER
        # =========================
        conn.execute("""
        CREATE TABLE IF NOT EXISTS embalagem_master (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            embalagem_code        TEXT NOT NULL,
            rev                   TEXT,
            cliente_id            INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
            material              TEXT NOT NULL,
            espessura_um          INTEGER,
            largura_mm            INTEGER,
            altura_mm             INTEGER,
            sanfona_mm            INTEGER NOT NULL DEFAULT 0,
            aba_mm                INTEGER NOT NULL DEFAULT 0,
            fita_tipo             TEXT NOT NULL DEFAULT 'nenhuma',
            impresso              INTEGER NOT NULL DEFAULT 0,
            layout_png            TEXT,
            transparencia         INTEGER,
            resistencia_mecanica  TEXT,
            vendido               INTEGER NOT NULL DEFAULT 0, -- 0 = genérico (não atrelado a cliente), 1 = vendido (cliente obrigatório)
            -- NCM opcional (8 dígitos) — pode não existir em bancos legados; bootstrap adiciona
            ncm                   TEXT CHECK (ncm IS NULL OR (length(ncm)=8 AND ncm GLOB '[0-9]*')),
            observacoes           TEXT,
            created_at            DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_emb_code ON embalagem_master(embalagem_code);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_emb_code_rev ON embalagem_master(embalagem_code, rev);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_emb_cliente ON embalagem_master(cliente_id);")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idxu_emb_code_rev ON embalagem_master(embalagem_code, IFNULL(rev,''));")

        # =========================
        # PEDIDOS & ITENS
        # =========================
        conn.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id            INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
            numero_pedido         TEXT,
            data_emissao          TEXT,
            data_prevista         TEXT,
            quantidade_tipo       TEXT,
            status                TEXT,
            preco_total           REAL,
            margem_toler_percent  REAL,
            ncm                   TEXT,
            created_at            DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pedidos_cliente ON pedidos(cliente_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pedidos_status  ON pedidos(status);")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idxu_pedidos_numero ON pedidos(numero_pedido);")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS pedido_itens (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id             INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
            embalagem_code        TEXT,
            rev                   TEXT,
            descricao             TEXT,
            qtd                   INTEGER,              -- quantidade pedida (interpretação depende de qtd_tipo)
            qtd_tipo              TEXT,                 -- 'UN' ou 'KG'
            preco_unit            REAL,                 -- preço unitário por unidade de venda escolhida
            preco_kg              REAL,                 -- preço referência por kg (para conversões)
            peso_unit_kg          REAL,                 -- peso estimado por unidade (kg) se qtd_tipo = UN
            margem_toler_percent  REAL,                 -- tolerância (mantido nome legado)
            -- Snapshot técnico da embalagem no momento da inserção
            snapshot_material         TEXT,
            snapshot_espessura_um     INTEGER,
            snapshot_largura_mm       INTEGER,
            snapshot_altura_mm        INTEGER,
            snapshot_sanfona_mm       INTEGER,
            snapshot_aba_mm           INTEGER,
            snapshot_fita_tipo        TEXT,
            snapshot_tratamento       INTEGER,          -- 0/1
            snapshot_tratamento_dinas INTEGER,
            snapshot_impresso         INTEGER,          -- 0/1
            -- Planejamento / produção
            anel_extrusao             TEXT,             -- referência de anel
            status_impressao          TEXT,             -- rascunho|pendente|em_processo|concluida
            extrusado                 INTEGER,          -- 0/1 preenchido via ordem de extrusão
            qtde_extrusada_kg         REAL              -- vindo de OE
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pedido_itens_pedido ON pedido_itens(pedido_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pedido_itens_emb ON pedido_itens(embalagem_code);")

        # Logs de pedido (auditoria simples)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS pedido_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id   INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
            user_id     INTEGER,
            acao        TEXT NOT NULL, -- CREATED / ITEM_ADDED / STATUS_CHANGED / etc
            detalhe_json TEXT,         -- JSON string (payload diff / snapshot)
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pedido_logs_pedido ON pedido_logs(pedido_id);")

        # =========================
        # IMPRESSÃO
        # =========================
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ordens_impressao (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id                INTEGER REFERENCES pedidos(id) ON DELETE SET NULL,
            numero                   TEXT,
            bobina_crua_lote         TEXT,
            cores                    TEXT,
            tinta_tipo               TEXT,
            cliche_ref               TEXT,
            velocidade_alvo_mpm      REAL,
            perdas_previstas_percent REAL,
            registro_toler_mm        REAL,
            status                   TEXT,
            created_at               DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_oi_pedido ON ordens_impressao(pedido_id);")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS bobinas_impressas (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            ordem_impressao_id INTEGER NOT NULL REFERENCES ordens_impressao(id) ON DELETE CASCADE,
            bobina_crua_id     INTEGER,
            etiqueta           TEXT,
            largura_mm         INTEGER,
            peso_bruto_kg      REAL,
            tara_tubo_kg       REAL,
            tara_embalagem_kg  REAL,
            peso_liquido_kg    REAL GENERATED ALWAYS AS
                                (COALESCE(peso_bruto_kg,0) - COALESCE(tara_tubo_kg,0) - COALESCE(tara_embalagem_kg,0)) STORED,
            sucata_kg          REAL,
            sucata_motivo      TEXT,
            qc2_status         TEXT,
            local_estoque      TEXT,
            created_at         DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bi_oi ON bobinas_impressas(ordem_impressao_id);")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS estoque_bobinas_impressas_mov (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            bobinas_impressa_id INTEGER NOT NULL REFERENCES bobinas_impressas(id) ON DELETE CASCADE,
            tipo                TEXT,
            qtd_kg              REAL,
            referencia          TEXT,
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_est_bi ON estoque_bobinas_impressas_mov(bobinas_impressa_id);")

        # =========================
        # PRODUÇÃO — CORTE & SOLDA
        # =========================
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ordens_producao (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id               INTEGER REFERENCES pedidos(id) ON DELETE SET NULL,
            numero                  TEXT,
            largura_mm              INTEGER,
            altura_mm               INTEGER,
            sanfona_mm              INTEGER,
            aba_mm                  INTEGER,
            fita_tipo               TEXT,
            resistencia_mecanica    TEXT,
            temp_solda_c            REAL,
            velocidade_corte_cpm    REAL,
            peso_min_bobina_kg      REAL,
            margem_erro_un_percent  REAL,
            status                  TEXT,
            created_at              DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_op_pedido ON ordens_producao(pedido_id);")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS producao_apontamentos (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            ordem_producao_id    INTEGER NOT NULL REFERENCES ordens_producao(id) ON DELETE CASCADE,
            bobina_impressa_id   INTEGER REFERENCES bobinas_impressas(id) ON DELETE SET NULL,
            peso_consumido_kg    REAL,
            peso_saida_kg        REAL,
            sucata_kg            REAL,
            sucata_motivo        TEXT,
            created_at           DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pa_op ON producao_apontamentos(ordem_producao_id);")

        # =========================
        # QUALIDADE
        # =========================
        conn.execute("""
        CREATE TABLE IF NOT EXISTS qc_inspecoes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo         TEXT,
            referencia_id INTEGER,
            amostra      TEXT,
            resultado    TEXT,
            observacoes  TEXT,
            fotos_json   TEXT,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # =========================
        # EXPEDIÇÃO
        # =========================
        conn.execute("""
        CREATE TABLE IF NOT EXISTS expedicoes (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id         INTEGER REFERENCES pedidos(id) ON DELETE SET NULL,
            modal             TEXT,
            transportadora    TEXT,
            destino           TEXT,
            data_saida        TEXT,
            veiculo_motorista TEXT,
            veiculo_placa     TEXT,
            rota_bairros      TEXT,
            comprovante_path  TEXT,
            romaneio_json     TEXT,
            status            TEXT,
            created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exped_pedido ON expedicoes(pedido_id);")

        # =========================
        # FUNÇÕES & FUNCIONÁRIOS (legado)
        # =========================
        conn.execute("""
        CREATE TABLE IF NOT EXISTS funcoes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nome        TEXT NOT NULL,
            area        TEXT,
            nivel       TEXT,
            descricao   TEXT,
            ativo       INTEGER DEFAULT 1
        );
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS funcionarios (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            nome                TEXT NOT NULL,
            cpf                 TEXT,
            matricula           TEXT,
            email               TEXT,
            telefone            TEXT,
            setor               TEXT,
            funcao_id           INTEGER REFERENCES funcoes(id) ON DELETE SET NULL,
            data_nascimento     TEXT,
            data_admissao       TEXT,
            data_inicio_funcao  TEXT,
            ativo               INTEGER DEFAULT 1,
            observacoes         TEXT
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_func_nome ON funcionarios(nome);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_func_funcao ON funcionarios(funcao_id);")

        # =========================
        # PARCEIROS (V2)
        # =========================
        conn.execute("""
        CREATE TABLE IF NOT EXISTS parceiros (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            razao_social       TEXT NOT NULL,
            cnpj               TEXT NOT NULL,
            tipo               TEXT DEFAULT 'fornecedor',
            endereco           TEXT,
            bairro             TEXT,
            complemento        TEXT,
            cep                TEXT,
            cidade             TEXT,
            estado             TEXT,
            pais               TEXT DEFAULT 'Brasil',
            contato_nome       TEXT,
            contato_email      TEXT,
            contato_telefone   TEXT,
            contato            TEXT,                          -- compat UI antiga (1 campo)
            representante      TEXT,
            email              TEXT,
            telefone           TEXT,
            observacoes        TEXT,
            servicos_json      TEXT DEFAULT '[]',
            ativo              INTEGER DEFAULT 1,
            created_at         DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_parc_cnpj ON parceiros(cnpj);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_parc_razao ON parceiros(razao_social);")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idxu_parceiros_cnpj ON parceiros(cnpj);")

        # =========================
        # COLABORADORES (novo) — COM acesso_nivel + usuario_id
        # =========================
        conn.execute("""
        CREATE TABLE IF NOT EXISTS colaboradores (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          nome TEXT NOT NULL,
          cpf TEXT UNIQUE,
          email TEXT,
          telefone TEXT,
          cidade TEXT,
          estado TEXT,                                -- UF (2 letras)
          cep TEXT,
          cargo TEXT,
          setor TEXT CHECK (setor IN ('producao','impressao','qualidade','pcp','logistica','manutencao','outro')) DEFAULT 'producao',
          vinculo TEXT NOT NULL CHECK (vinculo IN ('CLT','PJ','ESTAGIO')) DEFAULT 'CLT',
          parceiro_id INTEGER,
          ativo INTEGER NOT NULL DEFAULT 1,
          foto_url TEXT,
          data_admissao TEXT,
          pis TEXT,
          ctps_numero TEXT,
          ctps_serie TEXT,
          observacoes TEXT,
          -- acesso ao sistema
          usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
          acesso_nivel TEXT CHECK (acesso_nivel IN ('nenhum','leitura','operador','pcp','qualidade','admin')) DEFAULT 'nenhum',
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (parceiro_id) REFERENCES parceiros(id) ON DELETE RESTRICT,
          CONSTRAINT chk_colab_parceiro_pj CHECK (
            (vinculo = 'PJ' AND parceiro_id IS NOT NULL) OR
            (vinculo <> 'PJ' AND parceiro_id IS NULL)
          )
        );
        """)
        # índices sempre presentes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_colab_nome     ON colaboradores(nome);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_colab_setor    ON colaboradores(setor);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_colab_cargo    ON colaboradores(cargo);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_colab_uf       ON colaboradores(estado);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_colab_vinculo  ON colaboradores(vinculo);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_colab_ativo    ON colaboradores(ativo);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_colab_parceiro ON colaboradores(parceiro_id);")

        # índices condicionais (evita erro em bancos antigos que ainda não têm as colunas)
        cols_colab = _table_cols(conn, "colaboradores")
        if "usuario_id" in cols_colab:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_colab_usuario  ON colaboradores(usuario_id);")
        if "acesso_nivel" in cols_colab:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_colab_acesso   ON colaboradores(acesso_nivel);")

    return True


# ---------- bootstrap automático na subida ----------
def bootstrap_db():
    """
    1) Cria tudo se não existir (init_db)
    2) Aplica migrações aditivas simples (ADD COLUMN / VIEW / INDEX),
       para dar compat com bancos antigos — sem precisar rodar nada manualmente.
    """
    with get_conn() as conn:
        # 1) criação idempotente
        init_db()

        # 2) migrações ADITIVAS (seguras em SQLite)

        # parceiros: garantir campos usados pela UI
        for col_def in (
            "contato_nome TEXT",
            "contato_email TEXT",
            "contato_telefone TEXT",
            "contato TEXT"
        ):
            try:
                _add_col_if_missing(conn, "parceiros", col_def)
            except sqlite3.OperationalError:
                pass

        # parceiros: novo código interno sequencial (P00000..P99999)
        try:
            _add_col_if_missing(conn, "parceiros", "codigo_interno TEXT")
        except sqlite3.OperationalError:
            pass

        # clientes: garantir campos extras
        for col_def in ("comissao_percent REAL", "ncm_padrao TEXT", "observacoes TEXT"):
            try:
                _add_col_if_missing(conn, "clientes", col_def)
            except sqlite3.OperationalError:
                pass

        # colaboradores: garantir novos campos de acesso/usuario se faltarem
        for col_def in (
            "usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL",
            "acesso_nivel TEXT DEFAULT 'nenhum'"
        ):
            try:
                _add_col_if_missing(conn, "colaboradores", col_def)
            except sqlite3.OperationalError:
                pass

        # embalagem_master: adicionar coluna ncm se ausente (CHECK simplificado)
        try:
            _add_col_if_missing(conn, "embalagem_master", "ncm TEXT")
        except sqlite3.OperationalError:
            pass
        # embalagem_master: adicionar coluna vendido (flag 0/1)
        try:
            _add_col_if_missing(conn, "embalagem_master", "vendido INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        # pedidos: adicionar campos comerciais se ausentes (aditivo)
        for col_def in (
            "representante_id INTEGER REFERENCES colaboradores(id) ON DELETE SET NULL",
            "regime_venda TEXT",
            "comissao_percent REAL",
            "condicoes_comerciais TEXT",
            "representante_nome TEXT",
            "quantidade_planejada REAL",
            "embalagem_code TEXT",
            "preco_base REAL"
        ):
            try:
                _add_col_if_missing(conn, "pedidos", col_def)
            except sqlite3.OperationalError:
                pass

        # pedido_itens: adicionar campos snapshot e planejamento
        for col_def in (
            "qtd_tipo TEXT",
            "preco_kg REAL",
            "peso_unit_kg REAL",
            "snapshot_material TEXT",
            "snapshot_espessura_um INTEGER",
            "snapshot_largura_mm INTEGER",
            "snapshot_altura_mm INTEGER",
            "snapshot_sanfona_mm INTEGER",
            "snapshot_aba_mm INTEGER",
            "snapshot_fita_tipo TEXT",
            "snapshot_tratamento INTEGER",
            "snapshot_tratamento_dinas INTEGER",
            "snapshot_impresso INTEGER",
            "anel_extrusao TEXT",
            "status_impressao TEXT",
            "extrusado INTEGER",
            "qtde_extrusada_kg REAL"
        ):
            try:
                _add_col_if_missing(conn, "pedido_itens", col_def)
            except sqlite3.OperationalError:
                pass

        # numeradores: garantir linha para PED
        try:
            cur = conn.execute("SELECT 1 FROM numeradores WHERE nome='PED'").fetchone()
            if not cur:
                conn.execute("INSERT INTO numeradores (nome, ultimo) VALUES ('PED', 0)")
        except sqlite3.OperationalError:
            pass

        # (re)garantir índices de colaboradores
        for idx_stmt in (
            "CREATE INDEX IF NOT EXISTS idx_colab_nome     ON colaboradores(nome);",
            "CREATE INDEX IF NOT EXISTS idx_colab_setor    ON colaboradores(setor);",
            "CREATE INDEX IF NOT EXISTS idx_colab_cargo    ON colaboradores(cargo);",
            "CREATE INDEX IF NOT EXISTS idx_colab_uf       ON colaboradores(estado);",
            "CREATE INDEX IF NOT EXISTS idx_colab_vinculo  ON colaboradores(vinculo);",
            "CREATE INDEX IF NOT EXISTS idx_colab_ativo    ON colaboradores(ativo);",
            "CREATE INDEX IF NOT EXISTS idx_colab_parceiro ON colaboradores(parceiro_id);",
            "CREATE INDEX IF NOT EXISTS idx_colab_usuario  ON colaboradores(usuario_id);",
            "CREATE INDEX IF NOT EXISTS idx_colab_acesso   ON colaboradores(acesso_nivel);",
        ):
            conn.execute(idx_stmt)

        # view de saldo de bobinas impressas
        try:
            conn.execute("DROP VIEW IF EXISTS v_bobinas_impressas_saldo")
            conn.execute("""
            CREATE VIEW IF NOT EXISTS v_bobinas_impressas_saldo AS
            SELECT
              bi.id AS bobina_id,
              bi.ordem_impressao_id,
              bi.qc2_status,
              bi.peso_liquido_kg,
              COALESCE(bi.peso_liquido_kg,0)
                - COALESCE(SUM(CASE WHEN mov.tipo='SAIDA' THEN mov.qtd_kg ELSE 0 END),0) AS saldo_kg,
              MAX(bi.created_at) AS created_at
            FROM bobinas_impressas bi
            LEFT JOIN estoque_bobinas_impressas_mov mov
              ON mov.bobinas_impressa_id = bi.id
            GROUP BY bi.id, bi.ordem_impressao_id, bi.qc2_status, bi.peso_liquido_kg;
            """)
        except sqlite3.OperationalError:
            pass

        # índices únicos “de garantia”
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idxu_emb_code_rev ON embalagem_master(embalagem_code, IFNULL(rev,''));")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idxu_usuarios_email ON usuarios(email);")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idxu_parceiros_cnpj ON parceiros(cnpj);")

        # ===== Backfill e padronização de codigo_interno em parceiros =====
        # Regra: formato P00000..P99999 sequencial por ordem de id.
        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idxu_parceiros_codigo ON parceiros(codigo_interno);")
        except Exception:
            pass
        try:
            rows_p = conn.execute("SELECT id, codigo_interno FROM parceiros ORDER BY id ASC").fetchall()
            import re as _re
            max_seq_p = -1
            for r in rows_p:
                code = (r[1] or '').strip()
                m = _re.match(r'^P(\d{5})$', code or '')
                if m:
                    n = int(m.group(1))
                    if n > max_seq_p:
                        max_seq_p = n
            next_seq_p = max_seq_p + 1
            updates_p: list[tuple[str,int]] = []
            for r in rows_p:
                code = (r[1] or '').strip()
                if not _re.match(r'^P\d{5}$', code or ''):
                    if next_seq_p <= 99999:
                        new_code = f"P{next_seq_p:05d}"
                        updates_p.append((new_code, r[0]))
                        next_seq_p += 1
            if updates_p:
                conn.executemany("UPDATE parceiros SET codigo_interno=? WHERE id=?", updates_p)
        except Exception:
            pass

        # ===== Backfill e padronização de codigo_interno em clientes =====
        # Regra: formato C00000..C99999 sequencial por ordem de id.
        # 1. Garantir índice único opcional (não obrigatório no schema original) para evitar duplicidades futuras.
        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idxu_clientes_codigo ON clientes(codigo_interno);")
        except Exception:
            pass

        # 2. Carregar clientes sem código válido e atribuir sequência.
        # Consideramos válido se casa regex ^C\d{5}$.
        try:
            rows = conn.execute("SELECT id, codigo_interno FROM clientes ORDER BY id ASC").fetchall()
            # Extrair maior sufixo existente.
            import re as _re
            max_seq = -1
            for r in rows:
                code = (r[1] or '').strip()
                m = _re.match(r'^C(\d{5})$', code or '')
                if m:
                    num = int(m.group(1))
                    if num > max_seq:
                        max_seq = num
            next_seq = max_seq + 1
            updates: list[tuple[str,int]] = []
            for r in rows:
                code = (r[1] or '').strip()
                if not _re.match(r'^C\d{5}$', code or ''):
                    # atribuir novo
                    if next_seq <= 99999:
                        new_code = f"C{next_seq:05d}"
                        updates.append((new_code, r[0]))
                        next_seq += 1
            if updates:
                conn.executemany("UPDATE clientes SET codigo_interno=? WHERE id=?", updates)
        except Exception:
            # Falha silenciosa para não impedir subida; logs poderiam ser adicionados
            pass

    return True


# ---------- utilidades de código sequencial (pedidos) ----------
def gerar_codigo_pedido(conn: sqlite3.Connection) -> str:
    """Retorna próximo código PED-XXXXXX de forma transacional.

    Importante: chamar após BEGIN IMMEDIATE (ou dentro de get_conn antes de outras gravações)
    para reduzir risco de race. Implementação simples usando tabela numeradores.
    """
    # Garante existência do numerador
    conn.execute("INSERT OR IGNORE INTO numeradores (nome, ultimo) VALUES ('PED', 0)")
    row = conn.execute("SELECT ultimo FROM numeradores WHERE nome='PED'").fetchone()
    ultimo = row[0] if row else 0
    prox = ultimo + 1
    conn.execute("UPDATE numeradores SET ultimo=? WHERE nome='PED'", (prox,))
    return f"PED-{prox:06d}"
