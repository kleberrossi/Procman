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

        conn.execute("""
        CREATE TABLE IF NOT EXISTS pedido_itens (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id             INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
            embalagem_code        TEXT,
            rev                   TEXT,
            descricao             TEXT,
            qtd                   INTEGER,
            preco_unit            REAL,
            margem_toler_percent  REAL
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pedido_itens_pedido ON pedido_itens(pedido_id);")

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
        # FUNÇÕES & FUNCIONÁRIOS
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
        # parceiros: esquema novo separando contato_nome/email/telefone
        for col_def in ("contato_nome TEXT", "contato_email TEXT", "contato_telefone TEXT"):
            try:
                _add_col_if_missing(conn, "parceiros", col_def)
            except sqlite3.OperationalError:
                pass

        # clientes: garantir campos extras
        for col_def in ("comissao_percent REAL", "ncm_padrao TEXT", "observacoes TEXT"):
            try:
                _add_col_if_missing(conn, "clientes", col_def)
            except sqlite3.OperationalError:
                pass

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

    return True
