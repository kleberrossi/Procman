PRAGMA foreign_keys=ON;

-- =========================
-- 1) Clientes
-- =========================
CREATE TABLE IF NOT EXISTS clientes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  razao_social   TEXT NOT NULL,
  cnpj           TEXT NOT NULL,

  endereco       TEXT,                     -- logradouro/rua/número
  bairro         TEXT,
  complemento    TEXT,

  cep            TEXT,
  estado         TEXT,                     -- UF (2 letras)
  cidade         TEXT,
  pais           TEXT DEFAULT 'Brasil',

  codigo_interno TEXT,

  -- Contato do cliente
  contato_nome      TEXT,
  contato_email     TEXT,
  contato_telefone  TEXT,

  -- Representante interno + comissão
  representante     TEXT,
  comissao_percent  REAL DEFAULT 0,

  ncm_padrao     TEXT,
  observacoes    TEXT,
  created_at     TEXT DEFAULT (datetime('now'))
);

-- =========================
-- 2) Embalagem Master
-- =========================
CREATE TABLE IF NOT EXISTS embalagem_master (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  embalagem_code TEXT NOT NULL,
  rev TEXT,                                  -- pode ser NULL (app aceita vazio)
  cliente_id INTEGER,
  material TEXT NOT NULL,
  espessura_um INTEGER,                      -- pode ser NULL (form permite vazio)
  largura_mm INTEGER,                        -- pode ser NULL (form permite vazio)
  altura_mm INTEGER,                         -- pode ser NULL (form permite vazio)
  sanfona_mm INTEGER NOT NULL DEFAULT 0,
  aba_mm INTEGER NOT NULL DEFAULT 0,
  fita_tipo TEXT NOT NULL DEFAULT 'nenhuma', -- nenhuma | adesiva | hotmelt
  impresso INTEGER NOT NULL DEFAULT 0,       -- 0/1
  layout_png TEXT,                           -- caminho/arquivo
  transparencia INTEGER,                     -- 0..100 (0 válido)
  resistencia_mecanica TEXT,
  /* ===== NOVO: NCM por SKU (8 dígitos) =====
     Mantemos NULL no schema para migração suave; o app bloqueia emissão sem NCM. */
  ncm TEXT CHECK (ncm IS NULL OR (length(ncm)=8 AND ncm GLOB '[0-9]*')),
  observacoes TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE SET NULL
);


-- =========================
-- 3) Pedidos
-- =========================
CREATE TABLE IF NOT EXISTS pedidos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cliente_id INTEGER NOT NULL,
  numero_pedido TEXT NOT NULL,
  data_emissao TEXT NOT NULL,
  data_prevista TEXT,
  quantidade_tipo TEXT NOT NULL,            -- 'kg' | 'un'
  status TEXT NOT NULL DEFAULT 'RASCUNHO',   -- RASCUNHO|APROVADO|PLANEJADO|EM_EXECUCAO|CONCLUIDO
  preco_total REAL,
  margem_toler_percent REAL DEFAULT 0,
  ncm TEXT,
  FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);

-- =========================
-- 4) Itens do Pedido
-- =========================
CREATE TABLE IF NOT EXISTS pedido_itens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pedido_id INTEGER NOT NULL,
  embalagem_code TEXT NOT NULL,
  rev TEXT NOT NULL,
  descricao TEXT,
  qtd REAL NOT NULL,                         -- kg ou unidades
  preco_unit REAL,
  margem_toler_percent REAL,
  FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
);

-- =========================
-- 5) Impressão
-- =========================
CREATE TABLE IF NOT EXISTS ordens_impressao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pedido_id INTEGER NOT NULL,
  numero TEXT,
  bobina_crua_lote TEXT,
  cores TEXT,                                -- pode ser "4+2", etc.
  tinta_tipo TEXT,
  cliche_ref TEXT,
  velocidade_alvo_mpm REAL,
  perdas_previstas_percent REAL,
  registro_toler_mm REAL,
  status TEXT NOT NULL DEFAULT 'ABERTA',     -- ABERTA|EM_EXECUCAO|CONCLUIDA
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
);

CREATE TABLE IF NOT EXISTS bobinas_impressas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ordem_impressao_id INTEGER NOT NULL,
  bobina_crua_id INTEGER,
  etiqueta TEXT,
  largura_mm INTEGER,
  peso_bruto_kg REAL NOT NULL,
  tara_tubo_kg REAL DEFAULT 0,
  tara_embalagem_kg REAL DEFAULT 0,
  peso_liquido_kg AS (peso_bruto_kg - tara_tubo_kg - tara_embalagem_kg) STORED,
  sucata_kg REAL DEFAULT 0,
  sucata_motivo TEXT,
  qc2_status TEXT DEFAULT 'PENDENTE',   -- PENDENTE|APROVADA|QUARENTENA|REPROVADA
  local_estoque TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (ordem_impressao_id) REFERENCES ordens_impressao(id)
);

CREATE TABLE IF NOT EXISTS estoque_bobinas_impressas_mov (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bobinas_impressa_id INTEGER NOT NULL,
  tipo TEXT NOT NULL,                   -- ENTRADA|SAIDA
  qtd_kg REAL NOT NULL,
  referencia TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (bobinas_impressa_id) REFERENCES bobinas_impressas(id)
);

CREATE TABLE IF NOT EXISTS impressao_sucata_eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ordem_impressao_id INTEGER NOT NULL,
  bobinas_impressa_id INTEGER,
  kg REAL NOT NULL,
  motivo TEXT NOT NULL,                 -- setup|processo|limpeza|quebra|outro
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (ordem_impressao_id) REFERENCES ordens_impressao(id),
  FOREIGN KEY (bobinas_impressa_id) REFERENCES bobinas_impressas(id)
);

-- =========================
-- 6) Produção (Corte & Solda)
-- =========================
CREATE TABLE IF NOT EXISTS ordens_producao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pedido_id INTEGER NOT NULL,
  numero TEXT,
  largura_mm INTEGER NOT NULL,
  altura_mm INTEGER NOT NULL,
  sanfona_mm INTEGER NOT NULL DEFAULT 0,
  aba_mm INTEGER NOT NULL DEFAULT 0,
  fita_tipo TEXT NOT NULL,
  resistencia_mecanica TEXT,
  temp_solda_c REAL,
  velocidade_corte_cpm REAL,
  peso_min_bobina_kg REAL,
  margem_erro_un_percent REAL,
  status TEXT NOT NULL DEFAULT 'ABERTA',
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
);

CREATE TABLE IF NOT EXISTS producao_apontamentos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ordem_producao_id INTEGER NOT NULL,
  bobina_impressa_id INTEGER,
  peso_consumido_kg REAL DEFAULT 0,
  peso_saida_kg REAL DEFAULT 0,
  sucata_kg REAL DEFAULT 0,
  sucata_motivo TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (ordem_producao_id) REFERENCES ordens_producao(id),
  FOREIGN KEY (bobina_impressa_id) REFERENCES bobinas_impressas(id)
);

-- =========================
-- 7) QC (Genérico)
-- =========================
CREATE TABLE IF NOT EXISTS qc_inspecoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo TEXT NOT NULL,                   -- QC1|QC2|QC3|QC4
  referencia_id INTEGER NOT NULL,
  amostra TEXT,
  resultado TEXT NOT NULL,              -- APROVADA|QUARENTENA|REPROVADA
  observacoes TEXT,
  fotos_json TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

-- =========================
-- 8) Expedição
-- =========================
CREATE TABLE IF NOT EXISTS expedicoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pedido_id INTEGER NOT NULL,
  modal TEXT NOT NULL,                  -- transportadora|veiculo_proprio
  transportadora TEXT,
  destino TEXT,
  data_saida TEXT,
  veiculo_motorista TEXT,
  veiculo_placa TEXT,
  rota_bairros TEXT,
  comprovante_path TEXT,
  romaneio_json TEXT,
  status TEXT NOT NULL DEFAULT 'PENDENTE',
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
);

-- =========================
-- 9) Usuários (login)
-- =========================
CREATE TABLE IF NOT EXISTS usuarios (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  senha_hash TEXT NOT NULL,
  papel TEXT NOT NULL DEFAULT 'admin', -- admin | pcp | producao | qualidade | comercial
  ativo INTEGER NOT NULL DEFAULT 1,
  created_at TEXT DEFAULT (datetime('now'))
);

-- =========================
-- 9.1) Funções
-- =========================
CREATE TABLE IF NOT EXISTS funcoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL UNIQUE,
  area TEXT CHECK (area IN ('producao','impressao','qualidade','pcp','logistica','manutencao','outro')) DEFAULT 'producao',
  nivel TEXT,
  descricao TEXT,
  ativo INTEGER NOT NULL DEFAULT 1
);

-- =========================
-- 9.2) Funcionários (legado/uso interno)
-- =========================
CREATE TABLE IF NOT EXISTS funcionarios (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  cpf TEXT UNIQUE,
  matricula TEXT UNIQUE,
  email TEXT,
  telefone TEXT,
  setor TEXT CHECK (setor IN ('producao','impressao','qualidade','pcp','logistica','manutencao','outro')) DEFAULT 'producao',
  funcao_id INTEGER REFERENCES funcoes(id) ON DELETE SET NULL,
  data_nascimento TEXT,
  data_admissao TEXT,
  data_inicio_funcao TEXT,
  ativo INTEGER NOT NULL DEFAULT 1,
  observacoes TEXT
);

-- =========================
-- 10) PARCEIROS (V2 — do zero)
-- =========================
CREATE TABLE IF NOT EXISTS parceiros (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    razao_social      TEXT NOT NULL,
    cnpj              TEXT NOT NULL,
    tipo              TEXT DEFAULT 'fornecedor', -- fornecedor | transportadora | prestador
    endereco          TEXT,
    bairro            TEXT,
    complemento       TEXT,
    cep               TEXT,
    cidade            TEXT,
    estado            TEXT,                      -- UF
    pais              TEXT DEFAULT 'Brasil',
    contato_nome      TEXT,
    contato_email     TEXT,
    contato_telefone  TEXT,
    contato           TEXT,                      -- campo único usado pela UI atual
    representante     TEXT,
    email             TEXT,
    telefone          TEXT,
    observacoes       TEXT,
    servicos_json     TEXT DEFAULT '[]',         -- array de nomes (JSON)
    ativo             INTEGER DEFAULT 1,
    created_at        TEXT DEFAULT (datetime('now'))
);

-- =========================
-- 11) COLABORADORES (novo)
-- =========================
-- Regras:
-- - vinculo: CLT | PJ | ESTAGIO
-- - Se vinculo = 'PJ' => parceiro_id OBRIGATÓRIO (FK parceiros)
-- - Caso contrário, parceiro_id deve ser NULL
CREATE TABLE IF NOT EXISTS colaboradores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  cpf TEXT UNIQUE,                    -- máscara no app.js
  email TEXT,
  telefone TEXT,
  cidade TEXT,
  estado TEXT,                        -- UF (2 letras) — máscara no app.js
  cep TEXT,
  cargo TEXT,
  setor TEXT CHECK (setor IN ('producao','impressao','qualidade','pcp','logistica','manutencao','outro')) DEFAULT 'producao',
  vinculo TEXT NOT NULL CHECK (vinculo IN ('CLT','PJ','ESTAGIO')) DEFAULT 'CLT',
  parceiro_id INTEGER,                -- obrigatório quando vinculo='PJ'
  ativo INTEGER NOT NULL DEFAULT 1,
  foto_url TEXT,
  data_admissao TEXT,                 -- útil para CLT/estágio
  pis TEXT,                           -- CLT (máscara no app.js)
  ctps_numero TEXT,                   -- CLT (máscara no app.js)
  ctps_serie TEXT,                    -- CLT (máscara no app.js)
  observacoes TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (parceiro_id) REFERENCES parceiros(id) ON DELETE RESTRICT,
  CONSTRAINT chk_colab_parceiro_pj CHECK (
    (vinculo = 'PJ' AND parceiro_id IS NOT NULL) OR
    (vinculo <> 'PJ' AND parceiro_id IS NULL)
  )
);

-- =========================
-- ÍNDICES E VIEWS (consolidado)
-- =========================
CREATE UNIQUE INDEX IF NOT EXISTS idx_clientes_cnpj ON clientes(cnpj);
CREATE INDEX IF NOT EXISTS idx_clientes_cep ON clientes(cep);
CREATE INDEX IF NOT EXISTS idx_clientes_cidade_uf ON clientes(cidade, estado);

CREATE INDEX IF NOT EXISTS idx_pedidos_cliente ON pedidos(cliente_id);
CREATE INDEX IF NOT EXISTS idx_pedidos_status  ON pedidos(status);

CREATE INDEX IF NOT EXISTS idx_pedido_itens_pedido ON pedido_itens(pedido_id);

-- Embalagem: garantir unicidade considerando rev NULL/vazio
CREATE INDEX IF NOT EXISTS idx_embalagem_cliente ON embalagem_master(cliente_id);
CREATE UNIQUE INDEX IF NOT EXISTS idxu_emb_code_rev ON embalagem_master(embalagem_code, IFNULL(rev,''));

CREATE INDEX IF NOT EXISTS idx_oi_pedido ON ordens_impressao(pedido_id);
CREATE INDEX IF NOT EXISTS idx_bi_ordem ON bobinas_impressas(ordem_impressao_id);
CREATE INDEX IF NOT EXISTS idx_bi_qc2 ON bobinas_impressas(qc2_status);
CREATE INDEX IF NOT EXISTS idx_mov_bi ON estoque_bobinas_impressas_mov(bobinas_impressa_id);

CREATE INDEX IF NOT EXISTS idx_op_pedido ON ordens_producao(pedido_id);
CREATE INDEX IF NOT EXISTS idx_apont_op ON producao_apontamentos(ordem_producao_id);
CREATE INDEX IF NOT EXISTS idx_apont_bi ON producao_apontamentos(bobina_impressa_id);

CREATE INDEX IF NOT EXISTS idx_qc_tipo_ref ON qc_inspecoes(tipo, referencia_id);

CREATE INDEX IF NOT EXISTS idx_exp_pedido ON expedicoes(pedido_id);
CREATE INDEX IF NOT EXISTS idx_exp_status ON expedicoes(status);
CREATE INDEX IF NOT EXISTS idx_exp_modal ON expedicoes(modal);

CREATE UNIQUE INDEX IF NOT EXISTS idxu_parceiros_cnpj  ON parceiros(cnpj);
CREATE INDEX IF NOT EXISTS idx_parceiros_razao ON parceiros(razao_social);
CREATE INDEX IF NOT EXISTS idx_parceiros_cidade_uf ON parceiros(cidade, estado);
CREATE INDEX IF NOT EXISTS idx_parceiros_tipo  ON parceiros(tipo);

-- Colaboradores: índices p/ busca/UX
CREATE INDEX IF NOT EXISTS idx_colab_nome     ON colaboradores(nome);
CREATE INDEX IF NOT EXISTS idx_colab_setor    ON colaboradores(setor);
CREATE INDEX IF NOT EXISTS idx_colab_cargo    ON colaboradores(cargo);
CREATE INDEX IF NOT EXISTS idx_colab_uf       ON colaboradores(estado);
CREATE INDEX IF NOT EXISTS idx_colab_vinculo  ON colaboradores(vinculo);
CREATE INDEX IF NOT EXISTS idx_colab_ativo    ON colaboradores(ativo);
CREATE INDEX IF NOT EXISTS idx_colab_parceiro ON colaboradores(parceiro_id);

-- já há UNIQUE inline em usuarios(email), então não criamos outro índice UNIQUE extra aqui.

DROP VIEW IF EXISTS v_bobinas_impressas_saldo;
CREATE VIEW v_bobinas_impressas_saldo AS
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
