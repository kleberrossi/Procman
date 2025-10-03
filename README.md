# Procman

Aplicação Flask + SQLite para gestão de clientes, parceiros, colaboradores e embalagens.

## ⚠️ REGRAS CRÍTICAS DE DESENVOLVIMENTO

### 🚫 NUNCA ALTERAR SEM SOLICITAÇÃO EXPLÍCITA

#### Botões de Ação dos Pedidos (Ver/Editar/Excluir)
**LOCALIZAÇÃO**: Botões flutuantes que aparecem ao selecionar um pedido na lista.
- **ID**: `#pedido-actions-float`
- **Classes**: `.pedido-actions-float`
- **Posição**: `position: fixed; top: 0; right: 72px`
- **Estrutura**: 3 botões com `data-action="view|edit|delete"`

**CARACTERÍSTICAS INTOCÁVEIS**:
- Posicionamento CSS (`--pedido-float-right: 72px`)
- Coordenadas fixas (`top: 0`)
- Estrutura HTML dos botões
- Comportamento de visibilidade (`.is-visible`)
- Z-index (1200)

**⚡ VIOLAÇÃO DESTA REGRA É PROIBIDA** - Esses botões devem permanecer exatamente onde estão e como estão, a menos que seja solicitada alteração EXPLÍCITA.

---

## Visão Geral
- Backend: Flask (rotas síncronas simples) + SQLite3 com *bootstrap* defensivo (adiciona colunas/índices ausentes sem migrations formais).
- Frontend: Jinja2 + CSS custom (`modern-style.css`) + JS modular simples via namespace `App.*`.
- Códigos internos sequenciais para entidades (ex: Clientes `C00001`, Parceiros `P00001`).
- Formulários dinâmicos com validação progressiva e feedback visual (App.Notice + flashes Flask).

## Mudanças Recentes Principais
| Data (aprox) | Área | Resumo |
|--------------|------|--------|
| Recente | Parceiros | Inclusão de código interno `P00000` com retro-preenchimento e índice único. |
| Recente | Colaboradores | Abreviação de nome (primeiro + último), novos campos CPF / nível de acesso / usuário vinculado, tratamento de CPF duplicado, melhoria de validação e flashes unificados. |
| Recente | Layout | Ajustes de grid e colunas (clientes, parceiros, colaboradores) para consistência; formatação `Cidade-UF`. |
| Recente | Embalagens | Refatoração de toggles Sim/Não para checkboxes estilizados acessíveis + novo flag `vendido` que torna `cliente` condicionalmente obrigatório. |
| Recente | DB | Colunas defensivas `ncm` e `vendido` adicionadas se ausentes; documentação de filosofia de *bootstrap*. |
| 2025-10 | UI / Listas | Alias de classes sem `-v2`, criação de utilitários base (`list-header-base`, `list-row-base`), token unificado de foco `--focus-ring-color`. |
| 2025-10 | UI / Status | Componente unificado `.status-chip` substituindo `.status-badge` e `.status-pill`. |
| 2025-10 | UI / Listas | Remoção definitiva dos blocos `-v2` e dos aliases de migração (clientes, embalagens, parceiros, colaboradores). |

## Migração de Listas (v2 -> base)
As listas de Clientes, Embalagens, Parceiros e Colaboradores possuíam sufixo `-v2` e wrapper `cwb-v2` para uma segunda geração de layout.

### Objetivos
- Remover sufixos de versão do markup final.
- Reduzir duplicação de CSS extraindo padrões em classes base.
- Padronizar comportamento de foco/hover com um único token.

### Fases (Executadas)
1. Aliases CSS: adição de seletores neutros (ex: `.list-header.clientes`) coexistindo com `.clientes-v2`. (CONCLUÍDO)
2. Templates e JS: inclusão de novas classes lado a lado (ex: `cwb-v2 cwb clientes-v2 clientes`). (CONCLUÍDO)
3. Utilidades base: criação de `.list-header-base`, `.list-row-base`, `.list-cells-base`, `.list-actions-base`. (CONCLUÍDO)
4. Remoção de blocos `-v2` + aliases após verificação visual. (CONCLUÍDO 2025-10)
5. Unificação de tokens de foco (substituição de `--accent-focus` por `--focus-ring-color`). (PARCIAL – linhas base já usam token novo; restam revisões pontuais fora do escopo de listas)

### Situação Atual
- Código fonte não contém mais seletores `-v2` ativos (apenas em diretórios `Backup/` ou `Mockup/`).
- CSS reduzido: blocos duplicados e aliases removidos.
- Token de foco aplicado às linhas das listas (`.list-row-base`).

### Próximos Passos Relacionados
- Revisar mini-listas / componentes que ainda usam `-v2` (se existirem) antes de remover qualquer CSS residual nesses contextos.
- Converter eventuais usos restantes de `--accent-focus` fora das listas para `--focus-ring-color`.

### Como Migrar uma Nova Lista
1. Estruture header + linhas com mesma grid e aplique `list-header-base` e `list-row-base`.
2. Use variáveis de gap específicas (`--<nome>-gap`) ou o genérico `--list-gap`.
3. Para colunas complexas, forneça `grid-template-columns` via CSS custom property e reutilize.

### Checklist para Remover `-v2` (Histórico)
- [x] Grep: nenhum `clientes-v2|embalagens-v2|parceiros-v2|colaboradores-v2` em templates/JS principais.
- [x] Todas as linhas e headers usam classes base (`list-header-base` / `list-row-base`).
- [x] Testes visuais OK em breakpoints relevantes.
- [x] README atualizado e changelog anotado.

## Token de Foco Unificado
`--focus-ring-color` substitui `--accent-focus` e `--btn-focus-ring`.

Uso:
```css
button:focus-visible { box-shadow:0 0 0 3px var(--focus-ring-color); }
```
Para ajustar toda a paleta de foco basta redefinir `--focus-ring-color` no tema (ex: modo dark).

## Componente de Status Unificado
Legacy: `.status-badge` (data-status) e `.status-pill`.
Novo: `.status-chip` com modificadores semânticos.

Exemplo:
```html
<span class="status-chip is-aprovado">Aprovado</span>
```

Estados disponíveis: `is-rascunho`, `is-aprovado`, `is-em_execucao`, `is-concluido`, `is-cancelado`.

### Estratégia de Migração de Status
1. Substituir criação de badges em templates/JS para usar `.status-chip`.
2. Manter legacy até grep não retornar mais `.status-badge` ou `.status-pill`.
3. Remover blocos antigos e seção de compatibilidade.

## Convenções Adicionais (UI)
| Item | Regra |
|------|-------|
| Foco | Sempre via `--focus-ring-color` |
| Linhas de lista | Altura = `var(--btn-h)` |
| Espaçamento vertical listas densas | gap 0 + separador 1px entre itens |
| Componente status | `.status-chip .is-<estado>` |
| Sufixos de versão | Evitar em produção; usar branch/feature flags ao invés de `-v2` |

## Componente Toggle (Refatorado)
Antes: pares de botões "Sim/Não" com lógica JS ad-hoc.
Agora: cada feature (ex: `impressao`, `fita`, `resistencia`, `transparencia`, `tratamento`, `vendido`) usa:
1. `<div class="tg tg-check" data-flag="NOME">` com um `<input type="checkbox">` visível.
2. `<input type="hidden" name="NOME_flag" value="0|1">` sincronizado.
3. JS (`App.EmbalagensForm`):
   - `bindCheckboxToggles()` faz o *wiring* de eventos.
   - `applyCheckboxStates()` aplica estado inicial, habilita/desabilita campos dependentes e ajusta atributo `required` do cliente quando `vendido=1`.
4. CSS (`.tg.tg-check`) fornece a aparência moderna (track + thumb) mantendo acessibilidade nativa.

Benefícios:
- Acessibilidade (checkbox padrão navegável por teclado, estados claros).
- Menos markup (1 controle em vez de 2 botões mutuamente exclusivos).
- Lógica unificada (config array + iteração).

## Regra de Negócio: Flag Vendido
- Campo `vendido` (INTEGER 0/1) em `embalagem_master`.
- Quando `vendido=1` => `cliente_id` torna-se obrigatório (UI e server-side).
- Quando `vendido=0` => `cliente_id` é enviado como `NULL` (ignorado se preenchido incidentalmente).
- Validação backend garante consistência caso JS seja contornado.

## Códigos Internos Sequenciais
- Padrão: `<PREFIXO><número zero-padded 5>` (ex: `C00012`, `P00007`).
- Gerados dentro de transação selecionando `MAX(codigo)` e incrementando de forma robusta via regex para garantir formato.
- Backfill: Após adicionar coluna, registros existentes recebem códigos incrementalmente estáveis (ordem por `id`).
- Futuros prefixos adicionais devem reutilizar a mesma utilidade.

## Filosofia de Bootstrap do Banco
- Em vez de migrações versionadas, a função de inicialização executa:
  - `CREATE TABLE IF NOT EXISTS` (schema base).
  - Para cada coluna nova crítica: `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` condicional.
  - Criação de índices ausentes (unique / performance) de modo idempotente.
- Vantagens: zero dependência externa, facilidade de deploy em ambiente simples.
- Risco: evolução estrutural pesada (drops/renames) exigirá abordagem formal ou script separado.

## Estrutura JS Modular
- `App.EmbalagensForm` concentra lógica do formulário de embalagens; padrões a replicar para outros formulários dinâmicos:
  - Armazenar seletor raiz e derivar elementos.
  - Definir uma `config` declarativa descrevendo campos/toggles.
  - Funções idempotentes para aplicar estado inicial (suporta re-render parcial).

## Plano de Evolução Proposto
1. Unificar Componente Checkbox Toggle
   - Extrair CSS para bloco genérico (`.toggle-switch`), aceitar tamanhos por CSS vars.
   - Criar helper JS reutilizável `App.ToggleGroup.init(container)` para futuras telas.
2. Limpeza de Código Legado
   - Remover classes/estilos obsoletos `.seg`, `.seg-btn` se não usados em outras telas.
   - Caça a funções JS mortas (ex: lógica antiga de setToggle se ainda existir). 
3. Padronização de Validação
   - Centralizar regras condicionais em pequena camada (ex: objeto `Validators` com funções puras) para facilitar teste.
4. Documentação Técnica Expandida
   - Adicionar seção "Guia de Contribuição" incluindo convenção de nomes de campos `_flag`, códigos sequenciais e padrão de mensagens de flash.
5. Testes (Alcance Inicial Leve)
   - Script Python simples para validar geração de código e comportamento de `vendido` (in-memory SQLite). 
6. Acessibilidade e UX
   - Adicionar `aria-describedby` nos checkboxes e estados focáveis claros (outline consistente).
7. Internacionalização / Strings
   - Mapear strings repetidas ("Salvar", "Cancelar", etc.) para futura camada i18n (facilita tradução).

## Próximos Passos Imediatos
- [ ] Remover estilos e JS legacy de toggles se confirmada ausência de uso.
- [ ] Adicionar testes leves (scripts utilitários) para códigos sequenciais e validação `vendido`.
- [ ] Criar módulo `App.ToggleSwitch` reutilizável.

## Convenções de Nomenclatura
| Tipo | Padrão |
|------|--------|
| Código Interno | `^[A-Z]\d{5}$` |
| Campos booleanos persistidos | INTEGER 0/1 + sufixo `_flag` no form quando necessário shadow/hidden |
| Tabelas | snake_case singular (ex: `embalagem_master`) |

## Como Rodar
1. (Opcional) Criar virtualenv Python >= 3.11.
2. Instalar dependências: `pip install -r requirements.txt`.
3. Executar `python app.py` (ou `run.bat` em Windows se configurado) — a inicialização fará bootstrap do banco e colunas.

### Testes Automatizados

Suite de testes (pytest) cobre fluxo de Pedidos: numeração, transições de status, bloqueios pós-aprovação, snapshots imutáveis, métricas, revisão (rev) e logs principais.

Executar todos os testes:
```
pytest -q
```

Testar arquivo específico:
```
pytest tests/test_pedidos_flow.py::test_metrics_basico -q
```

Principais arquivos de teste:
- `tests/test_pedidos_flow.py` – casos base (sequencial, snapshot, métricas).
- `tests/test_pedidos_extra.py` – cobertura ampliada (delete, multi-itens, rev, bloqueios).
- `tests/test_pedidos_logs.py` – ordem e tipos de logs.

### Logs de Pedido
Eventos auditados: `CREATED`, `ITEM_ADDED`, `STATUS_CHANGED`, `OP_CREATED`, `ITEM_UPDATED`. Teste garante ordem relativa principal.

### Automação Local (tasks.py)

Arquivo utilitário `tasks.py` adiciona tarefas simples:

Executar aplicação:
```
python tasks.py run
```

Rodar testes silenciosos / verboso:
```
python tasks.py test
python tasks.py test -v
```

Pipeline local (placeholder para CI futura):
```
python tasks.py ci
```

Adicionar lint futuramente em `task_lint`.

## Notas de Segurança / Futuros Riscos
- Falta de autenticação robusta; nível de acesso inicial apenas representado no form (necessário enforcement server-side futuro).
- Validação atual basicamente server-side manual; considerar `WTForms` ou lib leve futuramente.

## Changelog Futuro
Usar este README como ponto central: acrescente entradas enxutas à tabela "Mudanças Recentes" quando features novas forem entregues.

---
Seção criada automaticamente para consolidar contexto das últimas alterações e oferecer base para contribuições futuras.

## Pós-Limpeza (Consolidação Final 2025-10)
- Mini-listas internas (itens de pedido / ordens de produção) migradas para classes sem sufixos (`.itens`, `.op-list`) usando padrões de header base.
- Removidos definitivamente estilos legacy de `.status-badge` e `.status-pill`; uso exclusivo de `.status-chip`.
- Token de foco unificado aplicado a todos os componentes de lista (incluindo mini versões).
- Eliminados sufixos `-v2` e `cwb-v2` em código ativo (restam apenas em diretórios `Backup/` e `Mockup/`).

### Política Anti-Regressão
1. Não reintroduzir sufixos de versão em produção (`-v2`, `-v3`, etc.). Usar branches/feature flags.
2. Novas listas devem:
   - Definir colunas via custom property (`--<nome>-cols` ou `--cols`).
   - Utilizar `list-header-base` e `list-row-base` (ou variante mini) + tokens de foco.
3. Status novos devem seguir o padrão `.status-chip is-<estado>` definindo cores via variáveis locais.
4. Antes de remover qualquer legado adicional, confirmar via grep e registrar no README.

### Próximos Passos Sugeridos (Opcional)
- Extração das mini-listas para um componente documentado (`.list-mini`).
- Script CI simples que falhe se encontrar regex `(cwb-v2|\w+-v2|status-badge|status-pill)` fora de `Backup|Mockup`.
- Revisão de acessibilidade: verificar contraste das cores de status com WCAG AA.

---

## Componente `.list-mini` (Mini Listas Unificadas)
Consolida padrões das mini listagens internas (itens de pedido e ordens de produção) antes definidos por combinações específicas (`.list-header.mini.itens`, `.list-header.mini.op-list`).

### Objetivos
- Eliminar duplicação de regras ao introduzir novas mini listagens internas.
- Usar a mesma semântica de tokens e comportamento de foco das listas grandes.
- Facilitar ajustes de densidade e colunas via CSS custom properties.

### Estrutura Base
```html
<div class="list-header list-mini" style="--cols: auto 1.4fr 0.6fr 0.6fr 0.6fr 0.9fr var(--actions-w,80px)">
   <div class="header-main">
      <div>Col 1</div>
      ...
   </div>
   <div class="actions-title">Ações</div>
</div>
<div class="list-mini-rows">
   <div class="list-row list-mini-row">
      <div>...</div>
   </div>
</div>
```

### Custom Properties
| Propriedade | Função | Default |
|-------------|--------|---------|
| `--cols` | Define as colunas (grid-template-columns) | `auto 1.4fr 0.6fr 0.6fr 0.6fr 0.9fr var(--actions-w, 80px)` |
| `--actions-w` | Largura da coluna de ações | `80px` |
| `--mini-gap` | Gap horizontal | `8px` |
| `--mini-h` | Altura mínima de header/linhas | `28px` |

### Variantes Legadas (Removidas)
Aliases anteriores `.list-header.mini.itens` e `.list-header.mini.op-list` foram eliminados (2025-10). Use apenas `.list-mini` com as custom properties.

### Guardrail de Legado
O teste `tests/test_guardrails.py` impede reintrodução de:
- `cwb-v2`
- `status-badge`
- `status-pill`
- Qualquer identificador terminando em `-v2`

Em caso de falha, ajuste o markup ou CSS para o padrão atual antes de prosseguir com o commit.

## Tokens Unificados de Listas (2025-10)
- `--list-gap`: gap horizontal padrão para qualquer grid de lista (substitui `--clientes-gap`, `--emb-gap`, etc. que agora são aliases apontando para ele).
- `--actions-3-icons-w`: largura padronizada calculada da coluna de ações para exatamente 3 ícones (substitui `<entidade>-actions-w` individuais que agora apenas referenciam este token).

Motivação: reduzir risco de divergência entre entidades e permitir ajuste global único (ex: aumentar densidade ou diminuir largura de ações universalmente).

Como usar em uma nova lista:
```css
.minha-lista-header{ grid-template-columns: var(--minha-cols, 1fr 1fr var(--actions-3-icons-w)); column-gap: var(--list-gap); }
```

---
