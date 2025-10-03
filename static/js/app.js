/* static/js/app.js */
/* eslint-disable no-console */
(function (window, document) {
  const App = (window.App = window.App || {});

  /* ========== Slot de aviso: realocar após .main-title ========== */
  document.addEventListener('DOMContentLoaded', () => {
    try {
      const slot = document.getElementById('global-notice-slot');
      const title = document.querySelector('.app-main h1.main-title');
      if (slot && title && title.nextElementSibling !== slot) {
        title.insertAdjacentElement('afterend', slot);
        slot.classList.add('notice-slot-inline');
      }
    } catch (e) { /* silencioso */ }
  });

  /* ===========================
   * Utils / Formatters / Masks
   * =========================== */
  const Util = (App.Util = {
    safe: (v) => (v == null ? "" : String(v)),

    icones() {
      if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
    },

    debounce(fn, wait = 200) {
      let t;
      return (...args) => {
        clearTimeout(t);
        t = setTimeout(() => fn.apply(null, args), wait);
      };
    },

    onlyDigits(s) {
      return String(s || "").replace(/\D/g, "");
    },

    formatCNPJ(val) {
      const d = Util.onlyDigits(val).slice(0, 14);
      if (!d) return "";
      if (d.length <= 2) return d;
      if (d.length <= 5) return d.slice(0, 2) + "." + d.slice(2);
      if (d.length <= 8) return d.slice(0, 2) + "." + d.slice(2, 5) + "." + d.slice(5);
      if (d.length <= 12)
        return d.slice(0, 2) + "." + d.slice(2, 5) + "." + d.slice(5, 8) + "/" + d.slice(8);
      return (
        d.slice(0, 2) +
        "." +
        d.slice(2, 5) +
        "." +
        d.slice(5, 8) +
        "/" +
        d.slice(8, 12) +
        "-" +
        d.slice(12, 14)
      );
    },

    formatPhoneBR(val) {
      const d = Util.onlyDigits(val).slice(0, 11);
      if (d.length <= 2) return d;
      if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`;
      if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
      return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
    },

    formatCEP(val) {
      const d = Util.onlyDigits(val).slice(0, 8);
      if (d.length <= 5) return d;
      return d.slice(0, 5) + "-" + d.slice(5);
    },

    formatNCM(val) {
      // 8 dígitos -> 0000.00.00
      const d = Util.onlyDigits(val).slice(0, 8);
      if (!d) return "";
      if (d.length <= 4) return d;
      if (d.length <= 6) return d.slice(0, 4) + "." + d.slice(4);
      return d.slice(0, 4) + "." + d.slice(4, 6) + "." + d.slice(6, 8);
    },

    attachMask(el, formatter) {
      if (!el) return;
      el.value = formatter(el.value);
      el.addEventListener("input", () => {
        const start = el.selectionStart;
        const before = el.value;
        el.value = formatter(el.value);
        const delta = el.value.length - before.length;
        const pos = Math.max(0, (start || 0) + (delta > 0 ? 1 : 0));
        try { el.setSelectionRange(pos, pos); } catch (_) {}
      });
    },

    attachDigitsLimit(el, maxLen = 8) {
      if (!el) return;
      el.addEventListener("input", () => {
        const d = Util.onlyDigits(el.value).slice(0, maxLen);
        if (el.value !== d) el.value = d;
      });
    },
  });

  /* ===========================
   * Global Notice (banner)
   * =========================== */
  const Notice = (App.Notice = (() => {
    let box, text, btn, timer;

    function grab() {
      // Garante existência do slot e card
      const slot = document.getElementById("global-notice-slot");
      if (slot) {
        box = slot.querySelector('#global-notice');
        if (!box) {
          box = document.createElement('div');
          box.id = 'global-notice';
          box.className = 'notice warn';
          box.hidden = true;
          box.setAttribute('role','alert');
          box.innerHTML = `\n            <i data-lucide="alert-triangle"></i>\n            <span id="global-notice-text"></span>\n            <button id="global-notice-close" class="notice-close" aria-label="Fechar aviso" type="button">×</button>`;
          slot.appendChild(box);
        }
        // Reposiciona imediatamente depois de .main-title se existir
        const title = document.querySelector('.main-title');
        if (title && title.nextElementSibling !== slot) {
          title.parentNode.insertBefore(slot, title.nextSibling);
        }
      }
      text = document.getElementById('global-notice-text');
      btn  = document.getElementById('global-notice-close');
      btn && btn.addEventListener('click', hide);
    }

    function ensureIcon(iconName, type){
      let iconEl = box?.querySelector('i[data-lucide]');
      if (!iconEl){
        iconEl = document.createElement('i');
        iconEl.setAttribute('data-lucide', iconName || 'info');
        box?.insertBefore(iconEl, text);
      } else {
        const desired = iconName || iconForType(type);
        if (iconEl.getAttribute('data-lucide') !== desired){
          iconEl.setAttribute('data-lucide', desired);
        }
      }
    }

    function iconForType(t){
      if (t === 'success') return 'check-circle';
      if (t === 'error') return 'x-circle';
      if (t === 'info') return 'info';
      if (t === 'warn' || t === 'warning') return 'alert-triangle';
      return 'info';
    }

  function show(message, { type = 'warn', timeout = 0, icon = null, closable = true } = {}) {
      if (!box || !text) return;
      clearTimeout(timer);
      box.classList.remove('info','success','warn','warning','error');
      box.classList.add(type);
      text.textContent = message;
      ensureIcon(icon, type);
      // botão de fechar
      btn = document.getElementById('global-notice-close');
      if (btn){
        if (!closable){
          btn.style.display = 'none';
          btn.removeEventListener('click', hide);
        } else {
          btn.style.display = '';
          btn.removeEventListener('click', hide);
          btn.addEventListener('click', hide, { once:true });
        }
      }
      box.hidden = false;
      if (!closable && (timeout == null || timeout === undefined)) timeout = 0;
      if (timeout > 0){
        timer = setTimeout(() => { hide(); }, timeout);
      }
      App.Util.icones?.();
    }

    function hide(){ if (box) box.hidden = true; }

    function init(){
      grab();
      window.addEventListener("notify", (e) => {
        if (!e.detail) return;
        show(e.detail.message, { type: e.detail.type, timeout: e.detail.timeout });
      });
    }
    return { init, show, hide };
  })());

  /* ===========================
   * Popover util (menus)
   * =========================== */
  const Pop = (App.Pop = {
    _open: null,
    _anchorBtn: null,

    closeAll() {
      if (Pop._open) Pop._open.hidden = true;
      document.getElementById("sort-menu")?.setAttribute("hidden", "true");
      document.getElementById("filter-menu")?.setAttribute("hidden", "true");
      document.querySelectorAll('.popover,[data-popover],[role="menu"]').forEach((el) => (el.hidden = true));
      Pop._open = null;
      Pop._anchorBtn = null;
    },

    open(pop, anchor) {
      if (!pop || !anchor) return;
      if (!pop.hidden && Pop._open === pop) {
        Pop.closeAll();
        return;
      }
      Pop.closeAll();
      const r = anchor.getBoundingClientRect();
      pop.style.position = "absolute";
      pop.style.top = window.scrollY + r.bottom + 6 + "px";
      pop.style.left = window.scrollX + r.left + "px";
      pop.hidden = false;
      Pop._open = pop;
      Pop._anchorBtn = anchor;
      setTimeout(() => {
        document.addEventListener("click", Pop._outsideOnce, { once: true });
      }, 0);
    },

    _outsideOnce(ev) {
      const p = Pop._open;
      if (!p) return;
      const t = ev.target;
      const insidePopover = p.contains(t);
      const onAnchor = Pop._anchorBtn && (t === Pop._anchorBtn || Pop._anchorBtn.contains(t));
      if (!insidePopover && !onAnchor) {
        Pop.closeAll();
      } else {
        document.addEventListener("click", Pop._outsideOnce, { once: true });
      }
    },
  });
  window.addEventListener("keydown", (e) => { if (e.key === "Escape") Pop.closeAll(); });
  window.addEventListener("scroll", Pop.closeAll, { passive: true });
  window.addEventListener("resize", Pop.closeAll);

  /* ===========================
   * Forms helpers (máscaras)
   * =========================== */
  const Forms = (App.Forms = {
    applyMasksIfAny() {
      const cliForm = document.getElementById("clientes-form");
      if (cliForm) Forms.applyClientes(cliForm);

      const parcForm = document.getElementById("parceiros-form");
      if (parcForm) Forms.applyParceiros(parcForm);
      // Embalagens: NCM tratado no módulo EmbalagensForm
    },

    applyClientes(formEl) {
      Util.attachMask(formEl.querySelector("#cnpj"), Util.formatCNPJ);
      Util.attachMask(formEl.querySelector("#contato_telefone"), Util.formatPhoneBR);
      Util.attachMask(formEl.querySelector("#cep"), Util.formatCEP);
      Util.attachMask(formEl.querySelector("#ncm_padrao"), Util.formatNCM);
      const uf = formEl.querySelector("#estado");
      if (uf) uf.addEventListener("input", () => { uf.value = (uf.value || "").toUpperCase().slice(0, 2); });
    },

    applyParceiros(formEl) {
      Util.attachMask(formEl.querySelector("#cnpj"), Util.formatCNPJ);
      Util.attachMask(formEl.querySelector("#contato_telefone"), Util.formatPhoneBR);
      Util.attachMask(formEl.querySelector("#cep"), Util.formatCEP);
      const uf = formEl.querySelector("#estado");
      if (uf) uf.addEventListener("input", () => { uf.value = (uf.value || "").toUpperCase().slice(0, 2); });
    },
  });

  /* ===========================
   * Página: Clientes (lista)
   * =========================== */
  App.Clientes = (function () {
    // Nova ordem visual: Código | Razão Social | CNPJ | Representante | Cidade-UF
    // Mantemos cidade e uf separados para filtros / ordenação fina (opcional) — exibimos fundidos.
    const FIELDS = [
      { key: "codigo", label: "Código", get: (c) => Util.safe(c.codigo_interno) },
      { key: "razao", label: "Razão Social", get: (c) => Util.safe(c.razao_social) },
      { key: "cnpj", label: "CNPJ", get: (c) => Util.safe(c.cnpj) },
      { key: "representante", label: "Representante", get: (c) => Util.safe(c.representante) },
      { key: "cidade", label: "Cidade", get: (c) => Util.safe(c.cidade || c.cidade_nome || c.city) },
      { key: "uf", label: "UF", get: (c) => Util.safe(c.estado || c.uf).toUpperCase() },
    ];

    const state = {
      data: [],
      sortField: "razao",
      sortDir: "asc",
      filters: { razao: new Set(), cnpj: new Set(), representante: new Set(), cidade: new Set(), uf: new Set() },
      filterActiveProp: "uf",
    };

    const ui = {};

    function grabUI() {
      ui.list = document.getElementById("clientes-list");
      ui.vazio = document.getElementById("sem-dados");

      ui.sortToggle = document.getElementById("sort-toggle");
      ui.sortFieldBtn = document.getElementById("sort-field");
      ui.sortMenu = document.getElementById("sort-menu");
      ui.sortFieldsList = document.getElementById("sort-fields-list");
      ui.sortLabel = document.getElementById("sort-label");
      ui.sortDir = document.getElementById("sort-dir");

      ui.filterBtn = document.getElementById("filter-btn");
      ui.filterMenu = document.getElementById("filter-menu");
      ui.filterProps = document.getElementById("filter-props");
      ui.filterValues = document.getElementById("filter-values");
      ui.filterApply = document.getElementById("filter-apply");
      ui.filterClearAll = document.getElementById("filter-clear-all");
      ui.filterBadge = document.getElementById("filter-badge");

      ui.busca = document.getElementById("busca-cli");
    }

    function fieldDef(key) { return FIELDS.find((f) => f.key === key) || FIELDS[0]; }

    function uniqueValuesFor(key) {
      const get = fieldDef(key).get;
      const s = new Set();
      for (const c of state.data) {
        let v = get(c);
        if (key === "cnpj") v = Util.formatCNPJ(v);
        if (!v || v === "-") continue;
        s.add(v);
      }
      return Array.from(s).sort((a, b) => String(a).localeCompare(String(b), "pt-BR", { sensitivity: "base", numeric: true }));
    }

    function updateSortChip() {
      ui.sortLabel.textContent = fieldDef(state.sortField).label;
      ui.sortDir.textContent = state.sortDir === "asc" ? "↑" : "↓";
    }

    function updateFilterBadge() {
      const total = Object.values(state.filters).reduce((n, set) => n + set.size, 0);
      if (total > 0) {
        ui.filterBadge.style.display = "inline-block";
        ui.filterBadge.textContent = total;
      } else {
        ui.filterBadge.style.display = "none";
        ui.filterBadge.textContent = "";
      }
    }

    function renderSortMenu() {
      ui.sortFieldsList.innerHTML = "";
      FIELDS.forEach((f) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "menu-item" + (f.key === state.sortField ? " active" : "");
        btn.textContent = f.label;
        btn.addEventListener("click", () => {
          state.sortField = f.key;
          Pop.closeAll();
          updateSortChip();
          renderClientes(getFilteredSortedData());
        });
        ui.sortFieldsList.appendChild(btn);
      });
      Util.icones();
    }

    function renderFilterProps() {
      ui.filterProps.innerHTML = "";
      FIELDS.forEach((f) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn pill" + (f.key === state.filterActiveProp ? " active" : "");
        b.textContent = f.label;
        b.addEventListener("click", () => {
          state.filterActiveProp = f.key;
          renderFilterProps();
          renderFilterValues();
        });
        ui.filterProps.appendChild(b);
      });
    }

    function renderFilterValues() {
      ui.filterValues.innerHTML = "";
      const key = state.filterActiveProp;
      const values = uniqueValuesFor(key);
      const selected = state.filters[key];

      if (values.length === 0) {
        const p = document.createElement("div");
        p.className = "menu-empty";
        p.textContent = "Sem valores disponíveis.";
        ui.filterValues.appendChild(p);
        return;
      }

      values.forEach((v) => {
        const id = "fv-" + key + "-" + btoa(unescape(encodeURIComponent(v))).replace(/=/g, "");
        const row = document.createElement("label");
        row.className = "menu-check";
        row.innerHTML = `
          <input type="checkbox" id="${id}" value="${v.replace(/"/g, "&quot;")}" ${selected.has(v) ? "checked" : ""}>
          <span class="ellipsis" title="${v.replace(/"/g, "&quot;")}">${v}</span>
        `;
        ui.filterValues.appendChild(row);
      });
    }

    // -------- normalização visual da lista (sem alterar CSS global)
    function normalizeClientesListStyles() {
      if (!ui.list) return;

      // Deixa links neutros (sem roxo visitado/sub-linha) dentro da lista
      ui.list.querySelectorAll('a').forEach((a) => {
        a.style.textDecoration = 'none';
        const cssVar = getComputedStyle(document.documentElement).getPropertyValue('--text').trim();
        if (cssVar) a.style.color = cssVar;
      });

      // CNPJ: sem espaçamento exagerado; sem forçar mono
      ui.list.querySelectorAll('.cnpj').forEach((el) => {
        el.style.letterSpacing = '0';
      });
    }

    function criaLinha(c) {
      const row = document.createElement("div");
  row.className = "list-row cwb clientes";

  const codigo = (Util.safe(c.codigo_interno) || "").trim() || "—";
  const razao = Util.safe(c.razao_social);
      const cnpjRaw = Util.safe(c.cnpj) || "-";
      const cnpjFmt = cnpjRaw === "-" ? "-" : Util.formatCNPJ(cnpjRaw);
      const repr = Util.safe(c.representante) || "—";
      const cidade = Util.safe(c.cidade || c.cidade_nome || c.city || "—");
      const uf = (Util.safe(c.estado || c.uf) || "—").toUpperCase();
  // Regras Cidade-UF: ambos -> Cidade-UF; só um -> mostra um; nenhum -> —
  const cidadeUf = (cidade !== "—" && uf !== "—") ? `${cidade}-${uf}` : (cidade !== "—" ? cidade : (uf !== "—" ? uf : "—"));
      const enderecoTitle = Util.safe(c.endereco || "").replace(/"/g, "&quot;");

      row.innerHTML = `
        <div class="row-main">
          <div class="ellipsis" title="${enderecoTitle}">${codigo}</div>
          <div class="ellipsis" title="${enderecoTitle}">${razao}</div>
          <div class="ellipsis cnpj">${cnpjFmt}</div>
            <div class="ellipsis">${repr}</div>
          <div class="ellipsis">${cidadeUf}</div>
        </div>
        <div class="list-actions cwb-v2">
          <a class="btn" href="/clientes/${c.id}" title="Ver"><i data-lucide="eye"></i></a>
          <a class="btn" href="/clientes/${c.id}/editar" title="Editar"><i data-lucide="edit"></i></a>
          <button class="btn danger" type="button" data-id="${c.id}" data-action="deletar" title="Deletar">
            <i data-lucide="trash-2"></i>
          </button>
        </div>
      `;
      return row;
    }

    function matchesFilters(c) {
      for (const f of FIELDS) {
        const set = state.filters[f.key];
        if (set && set.size) {
          let v = f.get(c);
          if (f.key === "cnpj") v = Util.formatCNPJ(v);
          if (!set.has(v)) return false;
        }
      }
      return true;
    }

    function getFilteredSortedData() {
      const q = (ui.busca?.value || "").toLowerCase();

      let arr = state.data.filter((c) => {
        if (!matchesFilters(c)) return false;
        if (!q) return true;

        const campos = [
          Util.safe(c.razao_social),
          Util.formatCNPJ(Util.safe(c.cnpj)),
          Util.safe(c.representante),
          Util.safe(c.cidade || c.cidade_nome || c.city),
          Util.safe(c.estado || c.uf),
        ].join(" ").toLowerCase();

        return campos.includes(q);
      });

      const fd = fieldDef(state.sortField);
      arr.sort((a, b) => {
        let va = fd.get(a);
        let vb = fd.get(b);
        if (state.sortField === "cnpj") {
          va = Util.onlyDigits(va);
          vb = Util.onlyDigits(vb);
        }
        const cmp = String(va).localeCompare(String(vb), "pt-BR", { sensitivity: "base", numeric: true });
        return state.sortDir === "asc" ? cmp : -cmp;
      });

      return arr;
    }

    function renderClientes(list) {
      ui.list.innerHTML = "";
      if (!list || list.length === 0) {
        ui.vazio.style.display = "";
        Util.icones();
        return;
      }
      ui.vazio.style.display = "none";
      for (const c of list) ui.list.appendChild(criaLinha(c));
      Util.icones();
      normalizeClientesListStyles();
    }

    async function carregaClientes() {
      ui.vazio.style.display = "none";
      try {
        const r = await fetch(`/api/clientes?ts=${Date.now()}`, {
          cache: 'no-store',
          headers: { 'Cache-Control': 'no-cache' }
        });
        if (!r.ok) throw new Error("Falha ao carregar clientes");
        state.data = await r.json();
        updateSortChip();
        updateFilterBadge();
        renderClientes(getFilteredSortedData());
      } catch (e) {
        ui.vazio.style.display = "";
        ui.vazio.textContent = "Erro ao carregar clientes.";
        console.error(e);
      }
    }

    function bindEvents() {
      ui.busca?.addEventListener("input", () => renderClientes(getFilteredSortedData()));

      ui.sortToggle?.addEventListener("click", () => {
        state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        updateSortChip();
        renderClientes(getFilteredSortedData());
      });

      ui.sortFieldBtn?.addEventListener("click", (ev) => {
        if (ui.sortMenu && !ui.sortMenu.hidden) {
          Pop.closeAll();
          return;
        }
        renderSortMenu();
        Pop.open(ui.sortMenu, ev.currentTarget.closest(".input-group") || ev.currentTarget);
      });

      ui.filterBtn?.addEventListener("click", (ev) => {
        if (ui.filterMenu && !ui.filterMenu.hidden) {
          Pop.closeAll();
          return;
        }
        renderFilterProps();
        renderFilterValues();
        Pop.open(ui.filterMenu, ev.currentTarget.closest(".input-group") || ev.currentTarget);
        Util.icones();
      });

      ui.filterApply?.addEventListener("click", () => {
        const key = state.filterActiveProp;
        const selected = new Set();
        ui.filterValues.querySelectorAll('input[type="checkbox"]:checked').forEach((ch) => selected.add(ch.value));
        state.filters[key] = selected;
        updateFilterBadge();
        Pop.closeAll();
        renderClientes(getFilteredSortedData());
      });

      ui.filterClearAll?.addEventListener("click", () => {
        Object.keys(state.filters).forEach((k) => state.filters[k].clear());
        ui.filterValues.querySelectorAll('input[type="checkbox"]').forEach((ch) => (ch.checked = false));
        updateFilterBadge();
        renderClientes(getFilteredSortedData());
      });

      // deletar (delegation)
      document.body.addEventListener("click", async (ev) => {
        const t = ev.target.closest('[data-action="deletar"]');
        if (!t) return;
        ev.preventDefault();
        const id = t.getAttribute("data-id");
        if (!id) return;
        if (!confirm("Deletar cliente #" + id + "?")) return;
        try {
          const resp = await fetch(`/api/clientes/${id}`, { method: "DELETE" });
          if (resp.ok) {
            state.data = state.data.filter((c) => String(c.id) !== String(id));
            renderClientes(getFilteredSortedData());
          } else {
            const err = await resp.json().catch(() => ({}));
            alert(err.error || "Erro ao deletar cliente.");
          }
        } catch (e) {
          console.error(e);
          alert("Falha de rede ao tentar deletar.");
        }
      });
    }

    function init() {
      grabUI();
      if (!ui.list) return; // página não é a de clientes
      carregaClientes();
      bindEvents();
    }

    return { init };
  })();

  /* ===========================
   * Página: Pedidos (lista + criação básica)
   * =========================== */
  App.Pedidos = (function(){
  /*
   * CONTRATO VISUAL / ESTRUTURAL LISTA DE PEDIDOS
   * - Header (.pedido-card.header) e linhas (.pedido-card) compartilham box model idêntico.
   * - Diferenças permitidas: tipografia (peso/tamanho/cor) e position:sticky no header.
  * - Colunas: definidas por --ped-cols (ou --ped-cols-frozen depois de congelar). Atualmente 8 colunas (sem coluna dedicada para ações).
  * - Ações: overlay absoluto (.pedido-actions) exibido em hover/focus-within; não participa do grid nem da medição/congelamento.
  * - Não aplicar width inline em cartões individuais (apenas congelar via variável CSS global do container) + expansão adaptativa opcional.
  * - Alinhamento: todas as colunas à esquerda conforme requisito atual (números usam tabular-nums para consistência).
   * - Debug: definir window.DEBUG_PEDIDOS = true para logar possíveis diferenças de header/linha.
   */
    const state = { data: [], logs: [] };
    /**
     * Aprova um pedido. Se pid for null cria antes usando payloadBase.
     * Retorna objeto {id,status} ou lança erro.
     */
    async function approve({ pid, payloadBase, formEl, btn }){
      const restore = btn ? btn.innerHTML : null;
      try {
        if (btn){ btn.disabled = true; btn.innerHTML = '<i data-lucide="loader"></i> Processando...'; App?.Util?.icones?.(); }
        // Criação se necessário
        if (!pid){
          const rCreate = await fetch('/api/pedidos', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payloadBase) });
          if (rCreate.status === 401) throw new Error('Sessão expirada');
          if (!rCreate.ok){ throw new Error('Falha ao criar ('+rCreate.status+')'); }
          const j = await rCreate.json();
          pid = j.id;
          if (!pid) throw new Error('Criação sem id');
        }
        const rStatus = await fetch(`/api/pedidos/${pid}/status`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({status:'APROVADO'}) });
        if (rStatus.status === 401) throw new Error('Sessão expirada');
        if (rStatus.status === 403) throw new Error('Sem permissão (PCP/Admin)');
        if (!rStatus.ok) throw new Error('Falha status ('+rStatus.status+')');
        const js = await rStatus.json();
        if (js.error) throw new Error(js.error);
        return { id: pid, status: js.status };
      } finally {
        if (btn){ btn.disabled = false; if (restore) { btn.innerHTML = restore; App?.Util?.icones?.(); } }
      }
    }
    const ui = {};

    function grabListUI(){
      ui.list = document.getElementById('pedidos-list');
  ui.scrollWrap = document.getElementById('pedidos-scroll-container');
  ui.empty = document.getElementById('pedidos-sem-dados');
  ui.busca = document.getElementById('busca-pedidos');
  ui.selStatus = document.getElementById('filtro-status');
  ui.selRep = document.getElementById('filtro-rep');
  ui.btnFiltrar = document.getElementById('btn-filtrar-pedidos');
  ui.btnRefresh = document.getElementById('btn-reload-pedidos');
  ui.subtitle = document.getElementById('pedidos-subtitle');
    }

    function buildQuery(){
      const params = new URLSearchParams();
      const q = (ui.busca?.value||'').trim(); if (q) params.set('q', q);
      const st = ui.selStatus?.value; if (st) params.set('status', st);
      const rep = ui.selRep?.value; if (rep) params.set('representante_id', rep);
      return params.toString();
    }

    let currentFetchSeq = 0; // sequenciador para descartar respostas antigas
    async function fetchList(){
      if (!ui.list) return;
      const mySeq = ++currentFetchSeq;
      const qs = buildQuery();
      // Sinaliza loading para reduzir flicker de fades: esconde-as
      if (ui.scrollWrap){
        ui.scrollWrap.dataset.loading = '1';
        // fade removido: antes apagava opacidade das bordas
      }
      try{
        const r = await fetch('/api/pedidos'+(qs?`?${qs}`:''));
        const rows = await r.json();
        if (mySeq !== currentFetchSeq) return; // resposta obsoleta
        state.data = Array.isArray(rows)? rows : [];
        renderList();
      }catch(_){ /* silent */ }
      finally {
        if (ui.scrollWrap){
          // Remove loading AFTER próximo frame garantindo unifyCardWidths já rodou
          requestAnimationFrame(()=>{
            if (mySeq === currentFetchSeq){
              delete ui.scrollWrap.dataset.loading;
            }
          });
        }
      }
    }

    function renderList(){
      if (!ui.list) return;
  // preserva primeira criança (header) se existir
  const header = ui.list.querySelector('.pedido-card.header');
  ui.list.innerHTML = '';
  if (header) ui.list.appendChild(header);

      const total = state.data.length;
      if (ui.subtitle) ui.subtitle.textContent = total ? `${total} pedido${total>1?'s':''}` : '';

      if (!total){
        if (ui.empty) ui.empty.hidden = false;
        return;
      } else if (ui.empty) ui.empty.hidden = true;

  const frag = document.createDocumentFragment();
  state.data.forEach(p => frag.appendChild(rowEl(p)));
  ui.list.appendChild(frag);
      App?.Util?.icones?.();
      // Novo fluxo: medir colunas e congelar (substitui unifyCardWidths)
      const widths = measureColumns(ui.list, 40);
  freezeColumns(ui.list, widths);
  // fade removido
      if (window.DEBUG_PEDIDOS) verifyHeaderParity();
      updateHeaderScrolledState();
  // Reposiciona a barra flutuante após primeira renderização
  requestAnimationFrame(()=> repositionFloatBar());
    }

    function measureColumns(listEl, limit = 40){
      const header = listEl.querySelector('.pedido-card.header');
      if (!header) return [];
      const rows = Array.from(listEl.querySelectorAll('.pedido-card:not(.header)')).slice(0, limit);
      const sample = [header, ...rows];
      const colCount = header.querySelectorAll(':scope > .cell').length;
      const max = new Array(colCount).fill(0);
      function scan(row){
        const cells = row.querySelectorAll(':scope > .cell');
        cells.forEach((c,i)=>{
          const w = c.getBoundingClientRect().width;
          if (w > max[i]) max[i] = w;
        });
      }
      sample.forEach(scan);
      return max.map(Math.ceil);
    }

    function freezeColumns(listEl, widths){
      if (!widths || !widths.length) return;
      const template = widths.map(w => w+'px').join(' ');
      listEl.style.setProperty('--ped-cols-frozen', template);
  // (fades removidos) anteriormente marcava readiness
  const wrap = ui.scrollWrap;
      // Após congelar, tentar expansão se caber na área útil (sem overflow horizontal)
      requestAnimationFrame(()=> maybeExpandColumns(listEl, widths));
  // Garantir eventual reposicionamento da barra após congelar
  requestAnimationFrame(()=> repositionFloatBar());
    }

    function maybeExpandColumns(listEl, widths){
      const wrap = ui.scrollWrap; if (!wrap || !widths || !widths.length) return;
      // Limpa qualquer expansão anterior
      listEl.style.removeProperty('--ped-cols-expanded');
      // Largura disponível (área útil) = largura interna do scroll container menos padding horizontal do card header (já incluso no card)
  const cs = getComputedStyle(document.querySelector('.pedidos-list-page') || wrap);
  const safetyVar = parseInt(cs.getPropertyValue('--ped-expand-safety')) || 8;
  const available = wrap.clientWidth - safetyVar; // já desconsidera barra de rolagem + folga configurável
      // Largura atual congelada somando gaps
      const gap = parseInt(getComputedStyle(listEl).getPropertyValue('--ped-col-gap')) || 0;
      const totalFrozen = widths.reduce((a,b)=>a+b,0) + gap * (widths.length - 1) + 16; // +16 aproxima padding horizontal (8+8)
      if (totalFrozen >= available) return; // Já ocupa tudo / overflow natural
      const extra = available - totalFrozen;
      if (extra < 12) return; // Ganho irrisório
      // Distribuir igualmente entre todas as colunas (exceto talvez a primeira muito pequena?)
      // Critério: incluir todas para simplicidade e preservar proporção visual linear.
      const addPer = Math.floor(extra / widths.length);
      if (addPer <= 0) return;
      const expanded = widths.map(w => (w + addPer) + 'px').join(' ');
      listEl.style.setProperty('--ped-cols-expanded', expanded);
  // Reposiciona barra após expansão (colunas podem ter mudado)
  requestAnimationFrame(()=> repositionFloatBar());
    }

    function updateOverflowVisibility(){
      const wrap = ui.scrollWrap; if (!wrap) return;
  // Scroll horizontal agora controlado puramente via CSS (fade removido)
      updateHeaderScrolledState();
  repositionFloatBar();
    }

    function updateHeaderScrolledState(){
      const wrap = ui.scrollWrap; if (!wrap) return;
      const scrolled = wrap.scrollTop > 0;
      wrap.classList.toggle('header-scrolled', scrolled);
    }

    function verifyHeaderParity(){
      try {
        const header = ui.list?.querySelector('.pedido-card.header');
        const firstRow = ui.list?.querySelector('.pedido-card:not(.header)');
        if (!header || !firstRow) return;
        const props = ['padding-left','padding-right','border-left-width','border-right-width','height','grid-template-columns'];
        const ch = getComputedStyle(header); const cr = getComputedStyle(firstRow);
        const diffs = props.filter(p => ch[p] !== cr[p]).map(p=> `${p}: header=${ch[p]} row=${cr[p]}`);
        if (diffs.length){ console.warn('[Pedidos][ParityDiff]', diffs); } else { console.info('[Pedidos] Header parity OK'); }
      } catch(_){}
    }

    // updateFades removido (sistema de fade desativado)
  ui.scrollWrap?.addEventListener('scroll', ()=> updateHeaderScrolledState());

  const debounceResize = App?.Util?.debounce?.(()=>updateOverflowVisibility(), 200);
    window.addEventListener('resize', ()=>debounceResize && debounceResize());

    // (removido overlay por linha) — reposicionamento da barra agora centralizado
    function repositionFloatBar(){
      if (!floatPid) return;
      const card = ui.list?.querySelector(`.pedido-card[data-pid="${floatPid}"]`);
      if (card) positionFloatBarFor(card); else hideFloatBar();
    }
    ui.scrollWrap?.addEventListener('scroll', ()=> repositionFloatBar(), { passive:true });

    // Observers para mudanças de tamanho ou mutações (dinâmico)
    let ro; if (window.ResizeObserver){
      ro = new ResizeObserver(()=> updateOverflowVisibility());
      ui.list && ro.observe(ui.list);
      ui.scrollWrap && ro.observe(ui.scrollWrap);
    }
    const mo = new MutationObserver(()=> updateOverflowVisibility());
    ui.list && mo.observe(ui.list, { childList:true, subtree:false });

    function fmtMoney(v){
      if (v == null || v === '') return '—';
      try { return Number(v).toLocaleString('pt-BR',{minimumFractionDigits:2, maximumFractionDigits:2}); } catch(_){ return v; }
    }

    function statusChip(status){
      if (!status) return '<span class="chip-status">—</span>';
      const cls = 'chip-status '+status.toLowerCase();
      return `<span class="${cls}">${status.replace(/_/g,' ').toLowerCase().replace(/(^|\s)\S/g, c=>c.toUpperCase())}</span>`;
    }

    function rowEl(p){
      const d = document.createElement('div');
      d.className = 'pedido-card';
      d.setAttribute('role','listitem');
      d.dataset.pid = p.id;

      // Campos base
      const numero = p.numero_pedido || '—';
      const cliente = p.cliente_nome || '—';
      const embalagemCode = p.embalagem_code || '—';
      const dataEmissaoRaw = p.data_emissao || p.data_criacao || null;
      const dataPrevRaw = p.data_prevista || null;

      function fmtDate(iso){
        if(!iso) return '—';
        const s = String(iso).slice(0,10); // yyyy-mm-dd
        const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
        if(!m) return iso;
        const yy = m[1].slice(2); // dois dígitos finais do ano
        return `${m[3]}/${m[2]}/${yy}`; // DD/MM/YY
      }
      const dataEmissao = fmtDate(dataEmissaoRaw);
      const dataPrev = fmtDate(dataPrevRaw);

      // Quantidade: soma itens -> fallback planejada
      let qtdBase = (typeof p.quantidade_un === 'number') ? p.quantidade_un : Number(p.quantidade_un || 0);
      if (!qtdBase && p.quantidade_planejada) {
        qtdBase = Number(p.quantidade_planejada) || 0;
      }
      const qtdFmt = qtdBase ? `${qtdBase.toLocaleString('pt-BR')} un.` : '—';

      const precoBase = p.preco_base != null ? fmtMoney(p.preco_base) : '—';
      // Valor total: prioriza campo calculado exib_total (servidor já decide entre soma itens ou base*planejada)
      // Fallbacks: preco_total -> preco_base -> '—'
      let valorNumber = null;
      if (p.exib_total != null && p.exib_total !== '') {
        valorNumber = Number(p.exib_total);
      } else if (p.preco_total != null && p.preco_total !== '') {
        valorNumber = Number(p.preco_total);
      } else if (p.preco_base != null && p.preco_base !== '') {
        valorNumber = Number(p.preco_base);
      }
      const valorTotal = valorNumber != null && !Number.isNaN(valorNumber) ? fmtMoney(valorNumber) : '—';
      const status = p.status || 'RASCUNHO';
      const statusNorm = status.toLowerCase();
      const statusClass = 'status-chip is-'+statusNorm.replace(/_/g,'_');
      const statusLabel = formatStatusLabel(status);

      // Montagem principal das células
      d.innerHTML = `
        <div class="cell data_emissao" title="${dataEmissao}">${dataEmissao}</div>
        <div class="cell data_prevista" title="${dataPrev}">${dataPrev}</div>
        <div class="cell numero" title="${numero}">${numero}</div>
        <div class="cell cliente" title="${escapeHtml(cliente)}">${escapeHtml(cliente)}</div>
        <div class="cell embalagem_code" title="${embalagemCode}">${embalagemCode}</div>
        <div class="cell quantidade" title="${qtdFmt}">${qtdFmt}</div>
        <div class="cell preco_base" title="${precoBase}">${precoBase}</div>
        <div class="cell valor" title="${valorTotal}">${valorTotal}</div>
        <div class="cell status" title="${statusLabel}"><span class="${statusClass}">${statusLabel}</span></div>`;
      return d;
    }


    function escapeHtml(s){
      return String(s||'').replace(/[&<>\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
    }

    function formatStatusLabel(st){
      if (!st) return '—';
      return st.replace(/_/g,' ').toLowerCase().replace(/(^|\s)\S/g, c=>c.toUpperCase());
    }


    // (Removido) ajuste dinâmico por JS — agora totalmente controlado por CSS minmax.


    function populateRepresentantes(){
      if (!ui.selRep) return;
      fetch('/api/colaboradores').then(r=>r.json()).then(rows => {
        const reps = rows.filter(c => /vendedor|rep|comercial/i.test(c.cargo||''));
        const opts = ['<option value="">Representante</option>'].concat(reps.map(r=>`<option value="${r.id}">${r.nome}</option>`));
        ui.selRep.innerHTML = opts.join('');
      }).catch(()=>{});
    }

    function bindListEvents(){
      if (!ui.list) return;
      const debounced = App.Util.debounce(()=>fetchList(), 350);
      ui.busca?.addEventListener('input', debounced);
      ui.selStatus?.addEventListener('change', fetchList);
      ui.selRep?.addEventListener('change', fetchList);
      ui.btnFiltrar?.addEventListener('click', fetchList);
      ui.btnRefresh?.addEventListener('click', fetchList);
      initFloatingBar();
    }

    /* ================= Floating Actions Bar (viewport fixed) ================= */
    let floatBar, floatPid = null;
    function ensureFloatBar(){
      if (floatBar) return floatBar;
      floatBar = document.getElementById('pedido-actions-float');
      if (!floatBar){
        floatBar = document.createElement('div');
        floatBar.id = 'pedido-actions-float';
        floatBar.setAttribute('role','toolbar');
        floatBar.setAttribute('aria-label','Ações do pedido selecionado');
        floatBar.innerHTML = `\n <button type="button" class="act-btn" data-action="view" aria-label="Ver pedido" title="Ver"><i data-lucide="eye"></i></button>\n <button type="button" class="act-btn" data-action="edit" aria-label="Editar pedido" title="Editar"><i data-lucide="edit"></i></button>\n <button type="button" class="act-btn" data-action="delete" aria-label="Excluir pedido" title="Excluir"><i data-lucide="trash-2"></i></button>`;
        document.body.appendChild(floatBar);
      }
      floatBar.classList.add('pedido-actions-float');
      App?.Util?.icones?.();
      floatBar.addEventListener('click', onFloatClick);
      // Navegação por teclado: setas esquerda/direita ciclam foco entre botões
      floatBar.addEventListener('keydown', e => {
        if (!['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) return;
        const buttons = Array.from(floatBar.querySelectorAll('button.act-btn'));
        if (!buttons.length) return;
        const idx = buttons.indexOf(document.activeElement);
        let next = idx;
        if (e.key === 'ArrowRight') next = (idx + 1) % buttons.length;
        if (e.key === 'ArrowLeft') next = (idx - 1 + buttons.length) % buttons.length;
        if (e.key === 'Home') next = 0;
        if (e.key === 'End') next = buttons.length - 1;
        if (next !== idx) {
          e.preventDefault();
          buttons[next].focus();
        }
      });
      return floatBar;
    }
    function onFloatClick(e){
      const btn = e.target.closest('button.act-btn'); if (!btn) return;
      if (!floatPid) return;
      const action = btn.getAttribute('data-action');
      if (action === 'view') { window.location.href = `/pedidos/${floatPid}`; return; }
      if (action === 'edit') { window.location.href = `/pedidos/${floatPid}/editar`; return; }
      if (action === 'delete') {
        // Tenta obter número do pedido para mensagem mais clara
        let numeroTxt = '';
        try {
          const numCell = document.querySelector(`.pedido-card[data-pid="${floatPid}"] .cell.numero`);
          if (numCell) numeroTxt = (numCell.textContent||'').trim();
        } catch(_){}
        const msg = numeroTxt && numeroTxt !== '—'
          ? `Excluir o pedido #${numeroTxt}? Esta ação não pode ser desfeita.`
          : 'Excluir este pedido? Esta ação não pode ser desfeita.';
        if (!confirm(msg)) return;
        fetch(`/api/pedidos/${floatPid}`, { method:'DELETE' })
          .then(r=>{
            if (r.status===204){
              state.data = state.data.filter(p=>String(p.id)!==String(floatPid));
              renderList();
              hideFloatBar();
              App?.Notice?.show?.('Pedido excluído',{type:'success', timeout:2000});
            } else {
              r.json().then(j=>App.Notice.show(j.error||'Falha ao excluir',{type:'error'}));
            }
          })
          .catch(()=>App.Notice.show('Erro de rede',{type:'error'}));
      }
    }
    function positionFloatBarFor(card){
      const fb = ensureFloatBar();
      const r = card.getBoundingClientRect();
      const h = fb.offsetHeight || 0;
      const top = Math.round(r.top + r.height/2 - h/2);
      fb.style.top = top + 'px';
      fb.setAttribute('aria-live','polite');
      fb.setAttribute('data-pid', card.dataset.pid || '');
      alignFloatBarRightEdge();
    }
    let hideTimer = null;
    function showFloatBar(){
      const fb = ensureFloatBar();
      if (hideTimer){ clearTimeout(hideTimer); hideTimer=null; }
      fb.classList.add('is-visible');
    }
    function scheduleHide(){
      if (hideTimer){ clearTimeout(hideTimer); }
      hideTimer = setTimeout(()=>{ if (floatBar){ floatBar.classList.remove('is-visible'); floatPid=null; } }, 180);
    }
    function initFloatingBar(){
      const wrap = ui.scrollWrap; if (!wrap || !ui.list) return;
      // Usar delegação por mouseover para reduzir jitter
      wrap.addEventListener('mouseover', e => {
        const card = e.target.closest('.pedido-card:not(.header)');
        if (!card) return;
        const pid = card.dataset.pid; if (!pid) return;
        if (pid !== floatPid){ floatPid = pid; positionFloatBarFor(card); }
        showFloatBar();
      });
      wrap.addEventListener('mouseleave', ()=> scheduleHide());
      // Manter barra se o mouse entrar nela
      document.addEventListener('mouseover', e => {
        if (!floatBar) return;
        if (e.target === floatBar || floatBar.contains(e.target)) {
          if (hideTimer){ clearTimeout(hideTimer); hideTimer=null; }
        }
      });
      document.addEventListener('mouseout', e => {
        if (!floatBar) return;
        if (e.target === floatBar || floatBar.contains(e.target)) {
          scheduleHide();
        }
      });
      // Ajustar posição em scroll/resize
      const reposition = () => repositionFloatBar();
      wrap.addEventListener('scroll', reposition, { passive:true });
      window.addEventListener('scroll', reposition, { passive:true });
      window.addEventListener('resize', reposition);
        window.addEventListener('resize', alignFloatBarRightEdge);
        alignFloatBarRightEdge();
    }

      // Alinha a borda direita da barra flutuante com a borda direita do bloco de ações do cabeçalho
      function alignFloatBarRightEdge(){
        if (!floatBar) return;
        const headerActions = document.querySelector('.page-head-actions');
        if (!headerActions) return;
        const rect = headerActions.getBoundingClientRect();
        const fbRect = floatBar.getBoundingClientRect();
        const desiredRight = rect.right; // ponto final das ações
        const newLeft = Math.round(desiredRight - fbRect.width);
        // Não altera dimensões, apenas posicionamento horizontal
        floatBar.style.left = newLeft + 'px';
        floatBar.style.right = 'auto';
      }
    
    /* ===== View-only (read-only) mode para página de visualização de pedido ===== */
    function detectPedidoViewMode(){
      // URL padrão de visualização (SOMENTE LEITURA) esperada: /pedidos/<id>
      // IMPORTANTE: /pedidos ou /pedidos/page carregam a LISTA e portanto não devem ativar este modo.
      // Se a aplicação ainda não possui rota /pedidos/<id>, este regex nunca acionará.
      // Depois de implementar a rota de detalhe, certifique-se de que o path real coincide com este padrão.
      return /^\/pedidos\/\d+$/.test(window.location.pathname);
    }
    function applyPedidoViewMode(){
      if (!detectPedidoViewMode()) return;
      // Considerar possíveis IDs de formulário existentes em diferentes templates
      const form = document.getElementById('pedido-form')
        || document.getElementById('pedidos-form')
        || document.getElementById('pedido-form-simples');
      if (!form) {
        // Como fallback, se a página claramente é de pedido, pode-se adicionar uma classe global;
        // não faz nada disruptivo sem o form.
        document.body.classList.add('pedido-view-noform');
        return;
      }
      // Evita aplicar duas vezes
      if (form.dataset.viewModeApplied) return;
      form.dataset.viewModeApplied = '1';
      form.classList.add('form-readonly');
      // Banner informativo
      let banner = document.querySelector('.view-mode-banner');
      if (!banner){
        banner = document.createElement('div');
        banner.className = 'view-mode-banner';
        banner.textContent = 'Visualização do pedido (somente leitura).';
        form.parentElement?.insertBefore(banner, form);
      }
      // Desabilita todos os campos de entrada (mantém links de navegação)
      form.querySelectorAll('input, select, textarea, button').forEach(el => {
        if (el.type === 'hidden') return;
        if (el.closest('.form-actions') && el.tagName === 'BUTTON') { el.hidden = true; return; }
        el.disabled = true;
        el.classList.add('is-readonly');
      });
      injectViewModeStyles();
    }
    function injectViewModeStyles(){
      if (document.getElementById('pedido-view-mode-style')) return;
      const st = document.createElement('style');
      st.id = 'pedido-view-mode-style';
      st.textContent = `/* View mode (auto-inject) */\n.view-mode-banner{margin:0 0 12px;padding:8px 12px;background:var(--bg-alt,#f5f5f5);border:1px solid var(--border,#d0d0d0);border-radius:6px;font-size:.85rem;color:var(--text-dim,#555);}\n.form-readonly .is-readonly{background:var(--bg-disabled,#f3f3f3)!important;cursor:not-allowed;opacity:.85;}\n.form-readonly .is-readonly::-webkit-calendar-picker-indicator{filter:grayscale(1);opacity:.6;}`;
      document.head.appendChild(st);
    }
    // Tenta aplicar no próximo frame (para garantir que o form já esteja no DOM após qualquer renderização do template)
    requestAnimationFrame(applyPedidoViewMode);
    // (Removido: ações popup e grade V2)

    // ---- Form de Novo Pedido ----
    function initForm(){
      const form = document.getElementById('pedido-form');
      if (!form) return;
      ui.aprovar = document.getElementById('btn-aprovar');
      ui.numeroSpan = document.getElementById('pedido-numero');
      ui.logsBox = document.getElementById('pedido-logs');
      ui.modal = document.getElementById('modal-item');
      ui.btnAddItem = document.getElementById('btn-add-item');
      ui.itemSave = document.getElementById('btn-item-save');
      ui.itemForm = document.getElementById('item-form');
      ui.itensList = document.getElementById('pedido-itens-list');
      ui.totalValor = document.getElementById('total-valor');
      ui.totalKg = document.getElementById('total-kg');
      ui.totalUn = document.getElementById('total-unidades');
      setupTabs();
      form.addEventListener('submit', onSubmitPedido);
      ui.btnAddItem?.addEventListener('click', () => openModal());
      ui.itemSave?.addEventListener('click', saveItemTemp);
      document.querySelectorAll('[data-close-modal]').forEach(btn => btn.addEventListener('click', closeAnyModal));
      ui.aprovar?.addEventListener('click', approvePedido);
      carregarClientesSelect();
      // Produção & Qualidade
      ui.btnCriarOP = document.getElementById('btn-criar-op');
      ui.btnRefreshOP = document.getElementById('btn-refresh-op');
      ui.opList = document.getElementById('op-rows');
      ui.modalOP = document.getElementById('modal-op');
      ui.opForm = document.getElementById('op-form');
      ui.btnOpSave = document.getElementById('btn-op-save');
      ui.btnCriarQC = document.getElementById('btn-add-qc');
      ui.btnRefreshQC = document.getElementById('btn-refresh-qc');
      ui.qcRows = document.getElementById('qc-rows');
      ui.modalQC = document.getElementById('modal-qc');
      ui.qcForm = document.getElementById('qc-form');
      ui.btnQcSave = document.getElementById('btn-qc-save');
      ui.btnCriarOP?.addEventListener('click', openModalOP);
      ui.btnOpSave?.addEventListener('click', saveOP);
      ui.btnRefreshOP?.addEventListener('click', loadOrdens);
      ui.btnCriarQC?.addEventListener('click', openModalQC);
      ui.btnQcSave?.addEventListener('click', saveQC);
      ui.btnRefreshQC?.addEventListener('click', loadQC);
    }

    function setupTabs(){
      const tabs = document.querySelectorAll('#pedido-tabs .tab, #pedido-tabs .tab-line');
      const panels = document.querySelectorAll('[data-tab-panel]');
      tabs.forEach(t => t.addEventListener('click', () => {
        const name = t.getAttribute('data-tab');
        tabs.forEach(o=>o.classList.toggle('active', o===t));
        panels.forEach(p=>{ p.hidden = p.getAttribute('data-tab-panel') !== name; });
        if (name === 'logs') loadLogs();
        if (name === 'producao') loadOrdens();
        if (name === 'qualidade') loadQC();
      }));
    }

    function carregarClientesSelect(){
      const sel = document.getElementById('cliente_id');
      if (!sel) return;
      fetch('/api/clientes').then(r=>r.json()).then(rows => {
        sel.innerHTML = '<option value="">(selecione)</option>' + rows.map(c=>`<option value="${c.id}">${c.codigo_interno||''} - ${c.razao_social}</option>`).join('');
      });
    }

    function onSubmitPedido(e){
      e.preventDefault();
      const fd = new FormData(e.target);
      const payload = Object.fromEntries(fd.entries());
      payload.cliente_id = Number(payload.cliente_id)||null;
      fetch('/api/pedidos',{method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)})
        .then(r=>r.json())
        .then(p => {
          if (p.error){ App.Notice.show(p.error,{type:'error'}); return; }
          ui.numeroSpan.textContent = p.numero_pedido;
          ui.aprovar.disabled = false;
          ui.statusAtual = p.status;
          ui.pedidoId = p.id;
          updateStatusBadge(p.status);
          updatePedidoMeta(payload.cliente_id);
          enablePostCreationButtons();
          loadLogs();
          loadMetrics();
          App.Notice.show('Pedido criado.', { type:'success', timeout:2500 });
        })
        .catch(()=>App.Notice.show('Falha ao criar pedido',{type:'error'}));
    }

    function enablePostCreationButtons(){
      if (!ui.pedidoId) return;
      ['btnCriarOP','btnRefreshOP','btnCriarQC','btnRefreshQC'].forEach(k=>{ if (ui[k]) ui[k].disabled = false; });
    }

    function openModal(){ if (ui.modal) ui.modal.hidden = false; }
    function closeModal(){ if (ui.modal) ui.modal.hidden = true; }
    function closeModalOP(){ if (ui.modalOP) ui.modalOP.hidden = true; }
    function closeModalQC(){ if (ui.modalQC) ui.modalQC.hidden = true; }
    function closeAnyModal(){ closeModal(); closeModalOP(); closeModalQC(); }

    function saveItemTemp(){
      if (!ui.pedidoId){ App.Notice.show('Crie o pedido antes de adicionar itens',{type:'warn'}); return; }
      const fd = new FormData(ui.itemForm);
      const payload = Object.fromEntries(fd.entries());
      payload.qtd = Number(payload.qtd)||0;
      payload.preco_unit = Number(payload.preco_unit)||0;
      payload.preco_kg = payload.preco_kg ? Number(payload.preco_kg) : null;
      payload.peso_unit_kg = payload.peso_unit_kg ? Number(payload.peso_unit_kg): null;
      fetch(`/api/pedidos/${ui.pedidoId}/itens`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)})
        .then(r=>r.json()).then(item => {
          if (item.error){ App.Notice.show(item.error,{type:'error'}); return; }
          appendItemRow(item);
          recalcTotais();
          closeModal();
          ui.itemForm.reset();
          App.Notice.show('Item adicionado',{type:'success', timeout:2000});
          loadMetrics();
        });
    }

    function appendItemRow(it){
      const r = document.createElement('div');
  r.className = 'list-row mini cwb-v2 cwb';
      r.innerHTML = `
        <div class="row-main">
          <div>${it.embalagem_code||'—'}</div>
          <div class="ellipsis" title="${it.descricao||''}">${it.descricao||'—'}</div>
          <div>${fmtMoney(it.preco_unit)}</div>
          <div>${fmtMoney(it.preco_kg)}</div>
          <div>${it.qtd||0} ${it.qtd_tipo||''}</div>
          <div>${it.status_impressao||'—'}</div>
        </div>
        <div class="list-actions cwb-v2">
          <button class="btn danger" type="button" data-del-item="${it.id||''}"><i data-lucide="trash-2"></i></button>
        </div>`;
      ui.itensList.appendChild(r);
      App.Util.icones();
      (ui.itens || (ui.itens=[])).push(it);
      r.querySelector('[data-del-item]')?.addEventListener('click', () => deleteItem(it));
      updateItensCount();
    }

    function recalcTotais(){
      const itens = ui.itens || [];
      let totalValor = 0, totalKg=0, totalUn=0;
      itens.forEach(it => {
        totalValor += (Number(it.preco_unit)||0) * (Number(it.qtd)||0);
        if (it.qtd_tipo === 'KG') totalKg += Number(it.qtd)||0; else if (it.peso_unit_kg) totalKg += (Number(it.qtd)||0) * Number(it.peso_unit_kg);
        if (it.qtd_tipo === 'UN') totalUn += Number(it.qtd)||0; else if (it.peso_unit_kg && it.peso_unit_kg>0) totalUn += Math.round((Number(it.qtd)||0)/it.peso_unit_kg);
      });
      ui.totalValor.textContent = fmtMoney(totalValor);
      ui.totalKg.textContent = totalKg.toLocaleString('pt-BR',{minimumFractionDigits:3, maximumFractionDigits:3});
      ui.totalUn.textContent = totalUn.toLocaleString('pt-BR');
    }

    function approvePedido(){
      if (!ui.pedidoId) return;
      fetch(`/api/pedidos/${ui.pedidoId}/status`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({status:'APROVADO'})})
        .then(r=>r.json()).then(resp => {
          if (resp.error){ App.Notice.show(resp.error,{type:'error'}); return; }
          ui.statusAtual = resp.status;
          ui.aprovar.disabled = true;
          ui.btnAddItem.disabled = true;
          enablePostCreationButtons();
          updateStatusBadge(resp.status);
          App.Notice.show('Pedido aprovado',{type:'success', timeout:2500});
          loadLogs();
          loadMetrics();
        });
    }

    function deleteItem(it){
      if (!ui.pedidoId || !it.id) return;
      if (!confirm('Remover item?')) return;
      fetch(`/api/pedidos/${ui.pedidoId}/itens/${it.id}`, {method:'DELETE'}).then(r => {
        if (r.status === 204){
          ui.itens = (ui.itens||[]).filter(x => x.id !== it.id);
          ui.itensList.innerHTML='';
          (ui.itens||[]).forEach(i=>appendItemRow(i));
          recalcTotais();
          App.Notice.show('Item removido',{type:'success', timeout:2000});
          loadLogs();
          loadMetrics();
          updateItensCount();
        } else {
          r.json().then(j=>App.Notice.show(j.error||'Falha ao remover',{type:'error'}));
        }
      });
    }

    function loadLogs(){
      if (!ui.pedidoId || !ui.logsBox) return;
      fetch(`/api/pedidos/${ui.pedidoId}/logs`).then(r=>r.json()).then(rows => { state.logs = rows; renderLogs(); });
    }

    function renderLogs(){
      if (!ui.logsBox) return;
      ui.logsBox.innerHTML = '';
      if (!state.logs.length){ ui.logsBox.innerHTML='<div class="log-empty">Sem logs.</div>'; return; }
      const frag = document.createDocumentFragment();
      state.logs.forEach(l => {
        const div = document.createElement('div');
        div.className = 'log-row';
        const det = (()=>{ try { return JSON.parse(l.detalhe_json||'{}'); } catch(_){ return {}; }})();
        div.innerHTML = `<span class="log-acao">${l.acao}</span> <span class="log-det">${escapeHtml(JSON.stringify(det))}</span> <span class="log-ts">${l.created_at||''}</span>`;
        frag.appendChild(div);
      });
      ui.logsBox.appendChild(frag);
    }

    function escapeHtml(s){
      return String(s).replace(/[&<>\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]||c));
    }

    // ==== Ordens de Produção ====
    function openModalOP(){ if (ui.modalOP) ui.modalOP.hidden = false; }
    function loadOrdens(){
      if (!ui.pedidoId || !ui.opList) return;
      fetch(`/api/pedidos/${ui.pedidoId}/ordens_producao`).then(r=>r.json()).then(rows => {
        ui.opList.innerHTML = '';
        if (!Array.isArray(rows) || !rows.length){ ui.opList.innerHTML = '<div class="empty-mini">Sem ordens.</div>'; return; }
        rows.forEach(o => ui.opList.appendChild(opRow(o)));
        App.Util.icones();
      });
    }
    function opRow(o){
      const d = document.createElement('div');
      d.className = 'list-row mini cwb-v2';
      d.innerHTML = `<div class="row-main">
        <div>${o.id}</div>
        <div>${o.largura_mm||'—'}</div>
        <div>${o.altura_mm||'—'}</div>
        <div>${o.sanfona_mm||'—'}</div>
        <div>${o.aba_mm||'—'}</div>
        <div>${o.velocidade_corte_cpm||'—'}</div>
        <div>${o.status||''}</div>
      </div>`;
      return d;
    }
    function saveOP(){
      if (!ui.pedidoId) return;
      const fd = new FormData(ui.opForm);
      const payload = Object.fromEntries(fd.entries());
      ['largura_mm','altura_mm','sanfona_mm','aba_mm','velocidade_corte_cpm'].forEach(k=>{ if(payload[k]) payload[k]=Number(payload[k]); });
      fetch(`/api/pedidos/${ui.pedidoId}/ordens_producao`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)})
        .then(r=>r.json()).then(op => {
          if (op.error){ App.Notice.show(op.error,{type:'error'}); return; }
          closeModalOP(); ui.opForm.reset();
          loadOrdens(); loadLogs();
          loadMetrics();
          App.Notice.show('Ordem criada',{type:'success', timeout:2000});
        });
    }

    // ==== Qualidade (QC) ====
    function openModalQC(){ if (ui.modalQC) ui.modalQC.hidden = false; }
    function loadQC(){
      if (!ui.pedidoId || !ui.qcRows) return;
      fetch(`/api/pedidos/${ui.pedidoId}/qc`).then(r=>r.json()).then(rows => {
        ui.qcRows.innerHTML = '';
        if (!Array.isArray(rows) || !rows.length){ ui.qcRows.innerHTML = '<tr><td colspan="6" style="padding:4px 6px;color:var(--text-dim);">Sem inspeções.</td></tr>'; return; }
        rows.forEach(q => ui.qcRows.appendChild(qcRow(q)));
      });
    }
    function qcRow(q){
      const tr = document.createElement('tr');
      const det = (q.observacoes||'').slice(0,60);
      tr.innerHTML = `<td style='padding:4px 6px;'>${q.id}</td>
        <td style='padding:4px 6px;'>${q.tipo||''}</td>
        <td style='padding:4px 6px;'>${q.amostra||''}</td>
        <td style='padding:4px 6px;'>${q.resultado||''}</td>
        <td style='padding:4px 6px;' title='${escapeHtml(q.observacoes||'')}'>${escapeHtml(det)}</td>
        <td style='padding:4px 6px;'>${q.created_at||''}</td>`;
      return tr;
    }
    function saveQC(){
      if (!ui.pedidoId) return;
      const fd = new FormData(ui.qcForm);
      const payload = Object.fromEntries(fd.entries());
      fetch(`/api/pedidos/${ui.pedidoId}/qc`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)})
        .then(r=>r.json()).then(q => {
          if (q.error){ App.Notice.show(q.error,{type:'error'}); return; }
          closeModalQC(); ui.qcForm.reset();
          loadQC(); loadLogs();
          loadMetrics();
          App.Notice.show('Inspeção registrada',{type:'success', timeout:2000});
        });
    }

    // ===== Metrics =====
    function loadMetrics(){
      if (!ui.pedidoId) return;
      fetch(`/api/pedidos/${ui.pedidoId}/metrics`).then(r=>r.json()).then(m => {
        if (m.error) return;
        renderMetrics(m);
      }).catch(()=>{});
    }
    function renderMetrics(m){
      const card = document.getElementById('metrics-card');
      const body = document.getElementById('metrics-body');
      if (!card || !body) return;
      card.hidden = false;
      const defs = [
        {k:'valor_total_calc', label:'Valor Calc. (R$)', fmt:v=>fmtMoney(v)},
        {k:'valor_total_registrado', label:'Valor Registro (R$)', fmt:v=>fmtMoney(v)},
        {k:'total_itens', label:'Itens', fmt:v=>v},
        {k:'total_qtd_un', label:'Qtd UN', fmt:v=>Number(v).toLocaleString('pt-BR')},
        {k:'total_qtd_kg', label:'Qtd KG Est.', fmt:v=>Number(v).toLocaleString('pt-BR',{minimumFractionDigits:3,maximumFractionDigits:3})},
        {k:'percentual_itens_impressos', label:'Itens Impressos (%)', fmt:v=>Number(v).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})},
      ];
      body.innerHTML = defs.map(d=>`<div class="metric-chip"><div class="m-label">${d.label}</div><div class="m-value">${d.fmt(m[d.k]||0)}</div></div>`).join('');
      const countSpan = document.getElementById('tab-itens-count');
      if (countSpan){ countSpan.textContent = m.total_itens||0; countSpan.hidden = (m.total_itens||0) === 0; }
    }

    function updateStatusBadge(status){
      const badge = document.getElementById('pedido-status-badge');
      if (!badge) return;
      const s = (status||'').toLowerCase();
      badge.dataset.status = s;
      badge.textContent = s.replace(/_/g,' ');
    }

    function updateItensCount(){
      const countSpan = document.getElementById('tab-itens-count');
      if (!countSpan) return;
      const n = (ui.itens||[]).length;
      countSpan.textContent = n;
      countSpan.hidden = n === 0;
    }

    function updatePedidoMeta(clienteId){
      const clienteNomeEl = document.getElementById('pedido-cliente-nome');
      if (!clienteNomeEl || !clienteId) return;
      fetch('/api/clientes').then(r=>r.json()).then(rows => {
        const c = rows.find(r=>r.id === Number(clienteId));
        if (c){ clienteNomeEl.textContent = c.razao_social; }
      }).catch(()=>{});
    }

    function init(){
      grabListUI();
      const isV2 = !!ui.listV2;
      console.log('[Pedidos] Init modo =', isV2 ? 'V2' : (ui.list ? 'LEGACY' : 'N/A'));
      if (isV2 || ui.list){
        // Limpa qualquer estilo inline legado de --ped-cols (caso tenha ficado de execuções anteriores)
        const rootPage = document.querySelector('.pedidos-list-page');
        if (rootPage && rootPage.style && rootPage.style.getPropertyValue('--ped-cols')) {
          rootPage.style.removeProperty('--ped-cols');
        }
        populateRepresentantes();
        bindListEvents();
        fetchList();
      }
      initForm();
      initContinuousTimeline();
    }

    // ===== Timeline contínua (form contínuo) =====
    function initContinuousTimeline(){
      const timeline = document.querySelector('.pedido-timeline');
      if (!timeline) return; // não está na versão contínua
      const links = Array.from(timeline.querySelectorAll('a[data-target]'));
      const sections = links.map(a => document.getElementById(a.getAttribute('data-target'))).filter(Boolean);
      if (!sections.length) return;

      // Scroll suave ao clicar
      links.forEach(a => {
        a.addEventListener('click', ev => {
          ev.preventDefault();
          const id = a.getAttribute('data-target');
            const target = document.getElementById(id);
          if (!target) return;
          const y = target.getBoundingClientRect().top + window.scrollY - 70; // offset do sticky + respiro
          window.scrollTo({ top:y, behavior:'smooth' });
        });
      });

      // Highlight com IntersectionObserver
      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting){
            const id = entry.target.id;
            links.forEach(l => l.parentElement.classList.toggle('active', l.getAttribute('data-target') === id));
            // Marcar visited
            links.forEach(l => { if (l.getAttribute('data-target') === id) l.parentElement.classList.add('visited'); });
          }
        });
      }, { root:null, rootMargin:'-50% 0px -40% 0px', threshold:0 });
      sections.forEach(sec => observer.observe(sec));
    }

    return { init, approve };
  })();

  /* ===========================
   * Página: Colaboradores (lista)
   * =========================== */
  App.Colaboradores = (function () {
    const state = {
      data: [],
      sortField: "nome",
      sortDir: "asc",
      filters: { setor: new Set(), vinculo: new Set(), parceiro: new Set(), ativo: new Set() },
      filterActiveProp: "setor",
    };
    const ui = {};

    // Mapeamentos (mantidos centralizados)
    const SETOR_LABELS = {
      producao: "Produção",
      impressao: "Impressão",
      qualidade: "Qualidade",
      pcp: "PCP",
      logistica: "Logística",
      manutencao: "Manutenção",
      outro: "Outro",
    };
    const VINCULO_LABELS = { CLT: "CLT", PJ: "PJ", ESTAGIO: "Estágio" };
    const labelSetor = (v) => SETOR_LABELS[v] || App.Util.safe(v);
    const labelVinculo = (v) => VINCULO_LABELS[v] || App.Util.safe(v);

    // Campos (ordenáveis) & Propriedades de filtro
    const FIELDS_COLAB = [
      { key: "nome", label: "Nome", get: (c) => App.Util.safe(c.nome) },
      { key: "vinculo", label: "Vínculo", get: (c) => labelVinculo(c.vinculo) },
      { key: "parceiro", label: "Parceiro", get: (c) => App.Util.safe(c.parceiro_nome || (c.parceiro_id ? "#" + c.parceiro_id : "")) },
      { key: "setor", label: "Setor", get: (c) => labelSetor(c.setor) },
      { key: "cargo", label: "Cargo", get: (c) => App.Util.safe(c.cargo) },
      { key: "ativo", label: "Ativo", get: (c) => Number(c.ativo ? 1 : 0) },
    ];
    const FILTER_PROPS_COLAB = [
      { key: "setor", label: "Setor", get: (c) => labelSetor(c.setor) },
      { key: "vinculo", label: "Vínculo", get: (c) => labelVinculo(c.vinculo) },
      { key: "parceiro", label: "Parceiro", get: (c) => App.Util.safe(c.parceiro_nome || (c.parceiro_id ? "#" + c.parceiro_id : "")) },
      { key: "ativo", label: "Ativo", get: (c) => (c.ativo ? "Sim" : "Não") },
    ];

    function fieldDef(key) { return FIELDS_COLAB.find((f) => f.key === key) || FIELDS_COLAB[0]; }
    function filterPropDef(key) { return FILTER_PROPS_COLAB.find((f) => f.key === key) || FILTER_PROPS_COLAB[0]; }

    function updateSortChip() {
      if (ui.sortLabel) ui.sortLabel.textContent = fieldDef(state.sortField).label;
      if (ui.sortDir) ui.sortDir.textContent = state.sortDir === "asc" ? "↑" : "↓";
    }
    function updateFilterBadge() {
      if (!ui.filterBadge) return;
      const total = Object.values(state.filters).reduce((n, s) => n + s.size, 0);
      if (total) {
        ui.filterBadge.style.display = "inline-block";
        ui.filterBadge.textContent = total;
      } else {
        ui.filterBadge.style.display = "none";
        ui.filterBadge.textContent = "";
      }
    }

    function uniqueValuesFor(key) {
      const get = filterPropDef(key).get;
      const s = new Set();
      for (const c of state.data) {
        const v = get(c);
        if (!v && v !== 0) continue;
        s.add(v);
      }
      return Array.from(s).sort((a, b) => String(a).localeCompare(String(b), "pt-BR", { sensitivity: "base", numeric: true }));
    }

    function renderSortMenu() {
      if (!ui.sortFieldsList) return;
      ui.sortFieldsList.innerHTML = "";
      FIELDS_COLAB.forEach((f) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "menu-item" + (f.key === state.sortField ? " active" : "");
        btn.textContent = f.label;
        btn.addEventListener("click", () => {
          state.sortField = f.key;
            App.Pop.closeAll();
          updateSortChip();
          render(getFilteredSortedData());
        });
        ui.sortFieldsList.appendChild(btn);
      });
      App.Util.icones();
    }

    function renderFilterProps() {
      if (!ui.filterProps) return;
      ui.filterProps.innerHTML = "";
      FILTER_PROPS_COLAB.forEach((p) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn pill" + (p.key === state.filterActiveProp ? " active" : "");
        b.textContent = p.label;
        b.addEventListener("click", () => {
          state.filterActiveProp = p.key;
          renderFilterProps();
          renderFilterValues();
        });
        ui.filterProps.appendChild(b);
      });
    }

    function renderFilterValues() {
      if (!ui.filterValues) return;
      ui.filterValues.innerHTML = "";
      const key = state.filterActiveProp;
      const values = uniqueValuesFor(key);
      const selected = state.filters[key];

      if (!values.length) {
        const p = document.createElement("div");
        p.className = "menu-empty";
        p.textContent = "Sem valores disponíveis.";
        ui.filterValues.appendChild(p);
        return;
      }
      values.forEach((v) => {
        const id = "fv-colab-" + key + "-" + btoa(unescape(encodeURIComponent(v))).replace(/=/g, "");
        const row = document.createElement("label");
        row.className = "menu-check";
        row.innerHTML = `
          <input type="checkbox" id="${id}" value="${String(v).replace(/"/g, '&quot;')}" ${selected.has(v) ? "checked" : ""}>
          <span class="ellipsis" title="${String(v).replace(/"/g, '&quot;')}">${v}</span>
        `;
        ui.filterValues.appendChild(row);
      });
    }

    function grabUI() {
      ui.list = document.getElementById("colaboradores-list");
      ui.vazio = document.getElementById("sem-dados-colab");
      ui.busca = document.getElementById("busca-colab");
      ui.sortToggle = document.getElementById("sort-toggle");
      ui.sortFieldBtn = document.getElementById("sort-field");
      ui.sortMenu = document.getElementById("sort-menu");
      ui.sortFieldsList = document.getElementById("sort-fields-list");
      ui.sortLabel = document.getElementById("sort-label");
      ui.sortDir = document.getElementById("sort-dir");
      ui.filterBtn = document.getElementById("filter-btn");
      ui.filterMenu = document.getElementById("filter-menu");
      ui.filterProps = document.getElementById("filter-props");
      ui.filterValues = document.getElementById("filter-values");
      ui.filterApply = document.getElementById("filter-apply");
      ui.filterClearAll = document.getElementById("filter-clear-all");
      ui.filterBadge = document.getElementById("filter-badge");
    }

    function criaLinha(c) {
      const row = document.createElement("div");
  row.className = "list-row cwb colaboradores";
      // Exibir apenas primeiro e último nome quando houver mais de dois componentes
      // Mantemos c.nome completo para ordenação e busca (FIELDS_COLAB.get) e só ajustamos a exibição.
      const nomeCompleto = App.Util.safe(c.nome || "-");
      let nome = nomeCompleto;
      if (c.nome) {
        const partes = String(c.nome).trim().split(/\s+/).filter(Boolean);
        if (partes.length > 2) {
          nome = App.Util.safe(partes[0] + " " + partes[partes.length - 1]);
        }
      }
      const vinc = labelVinculo(c.vinculo || "-");
      const parc = App.Util.safe(c.parceiro_nome || (c.parceiro_id ? "#" + c.parceiro_id : "—"));
      const setor = labelSetor(c.setor || "-");
      const cargo = App.Util.safe(c.cargo || "—");
      const situ = c.ativo ? "Ativo" : "Inativo";
      row.innerHTML = `
        <div class="row-main">
          <div class="ellipsis">${nome}</div>
          <div class="ellipsis">${vinc}</div>
          <div class="ellipsis">${parc || '—'}</div>
          <div class="ellipsis">${setor}</div>
          <div class="ellipsis">${cargo}</div>
          <div class="ellipsis">${situ}</div>
        </div>
        <div class="list-actions cwb-v2">
          <a class="btn" href="/colaboradores/${c.id}" title="Ver"><i data-lucide="eye"></i></a>
          <a class="btn" href="/colaboradores/${c.id}/editar" title="Editar"><i data-lucide="edit"></i></a>
          <button class="btn danger" type="button" data-id="${c.id}" data-action="deletar-colab" title="Deletar">
            <i data-lucide="trash-2"></i>
          </button>
        </div>`;
      return row;
    }

    function matchesFilters(c) {
      if (state.filters.setor.size && !state.filters.setor.has(labelSetor(c.setor))) return false;
      if (state.filters.vinculo.size && !state.filters.vinculo.has(labelVinculo(c.vinculo))) return false;
      if (state.filters.parceiro.size) {
        const pv = App.Util.safe(c.parceiro_nome || (c.parceiro_id ? "#" + c.parceiro_id : ""));
        if (!state.filters.parceiro.has(pv)) return false;
      }
      if (state.filters.ativo.size) {
        const av = c.ativo ? "Sim" : "Não";
        if (!state.filters.ativo.has(av)) return false;
      }
      return true;
    }

    function getFilteredSortedData() {
      const q = (ui.busca?.value || "").toLowerCase();
      let arr = state.data.filter((c) => {
        if (!matchesFilters(c)) return false;
        if (!q) return true;
        const campos = [
          c.nome,
          c.vinculo,
          c.setor,
          c.cargo,
          c.parceiro_nome,
          c.parceiro_id,
          c.email,
          c.telefone,
          c.cidade,
          c.uf,
        ]
          .map(App.Util.safe)
          .join(" ")
          .toLowerCase();
        return campos.includes(q);
      });

      const fd = fieldDef(state.sortField);
      arr.sort((a, b) => {
        let va = fd.get(a);
        let vb = fd.get(b);
        if (typeof va === "number" && typeof vb === "number") return state.sortDir === "asc" ? va - vb : vb - va;
        const cmp = String(va).localeCompare(String(vb), "pt-BR", { sensitivity: "base", numeric: true });
        return state.sortDir === "asc" ? cmp : -cmp;
      });
      return arr;
    }

    function render(list) {
      if (!ui.list) return;
      ui.list.innerHTML = "";
      if (!list || !list.length) {
        if (ui.vazio) ui.vazio.style.display = "";
        App.Util.icones();
        return;
      }
      if (ui.vazio) ui.vazio.style.display = "none";
      for (const c of list) ui.list.appendChild(criaLinha(c));
      App.Util.icones();
    }

    async function carregar() {
      if (ui.vazio) ui.vazio.style.display = "none";
      try {
        const r = await fetch(`/api/colaboradores?ts=${Date.now()}`);
        if (!r.ok) throw new Error("Falha ao carregar colaboradores");
        state.data = await r.json();
        updateSortChip();
        updateFilterBadge();
        render(getFilteredSortedData());
      } catch (e) {
        console.error(e);
        if (ui.vazio) {
          ui.vazio.style.display = "";
          ui.vazio.textContent = "Erro ao carregar colaboradores.";
        }
      }
    }

    function bind() {
      ui.busca?.addEventListener("input", () => render(getFilteredSortedData()));

      ui.sortToggle?.addEventListener("click", () => {
        state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        updateSortChip();
        render(getFilteredSortedData());
      });

      ui.sortFieldBtn?.addEventListener("click", (ev) => {
        if (ui.sortMenu && !ui.sortMenu.hidden) {
          App.Pop.closeAll();
          ui.sortFieldBtn?.setAttribute("aria-expanded", "false");
          return;
        }
        renderSortMenu();
        App.Pop.open(ui.sortMenu, ev.currentTarget.closest(".input-group") || ev.currentTarget);
        ui.sortFieldBtn?.setAttribute("aria-expanded", "true");
      });

      ui.filterBtn?.addEventListener("click", (ev) => {
        if (ui.filterMenu && !ui.filterMenu.hidden) {
          App.Pop.closeAll();
          ui.filterBtn?.setAttribute("aria-expanded", "false");
          return;
        }
        renderFilterProps();
        renderFilterValues();
        App.Pop.open(ui.filterMenu, ev.currentTarget.closest(".input-group") || ev.currentTarget);
        ui.filterBtn?.setAttribute("aria-expanded", "true");
        App.Util.icones();
      });

      ui.filterApply?.addEventListener("click", () => {
        const key = state.filterActiveProp;
        const selected = new Set();
        ui.filterValues?.querySelectorAll('input[type="checkbox"]:checked').forEach((ch) => selected.add(ch.value));
        state.filters[key] = selected;
        updateFilterBadge();
        App.Pop.closeAll();
        ui.filterBtn?.setAttribute("aria-expanded", "false");
        render(getFilteredSortedData());
      });

      ui.filterClearAll?.addEventListener("click", () => {
        Object.keys(state.filters).forEach((k) => state.filters[k].clear());
        ui.filterValues?.querySelectorAll('input[type="checkbox"]').forEach((ch) => (ch.checked = false));
        updateFilterBadge();
        render(getFilteredSortedData());
      });

      document.body.addEventListener("click", async (ev) => {
        const t = ev.target.closest('[data-action="deletar-colab"]');
        if (!t) return;
        ev.preventDefault();
        const id = t.getAttribute("data-id");
        if (!id) return;
        if (!confirm("Deletar colaborador #" + id + "?")) return;
        try {
          const resp = await fetch(`/api/colaboradores/${id}`, { method: "DELETE" });
          if (resp.ok) {
            state.data = state.data.filter((c) => String(c.id) !== String(id));
            render(getFilteredSortedData());
          } else {
            const err = await resp.json().catch(() => ({}));
            alert(err.error || "Erro ao deletar colaborador.");
          }
        } catch (e) {
          console.error(e);
          alert("Falha de rede ao tentar deletar.");
        }
      });
    }

    function init() {
      grabUI();
      if (!ui.list) return; // não está na página
      carregar();
      bind();
    }

    return { init };
  })();

  /* ===========================
   * Página: Embalagens (form)
   * =========================== */
  App.EmbalagensForm = (function () {
    let IS_VIEW = false;

    function setCardEnabled(cardId, enabled) {
      const card = document.getElementById(cardId);
      if (!card) return;
      card.classList.toggle("is-off", !enabled);

      if (IS_VIEW) return;

      card.querySelectorAll("input, select, textarea").forEach((el) => {
        el.disabled = !enabled || el.hasAttribute("data-always-disabled");
        if (!enabled) el.setAttribute("aria-disabled", "true");
        else el.removeAttribute("aria-disabled");
      });
      if (cardId === "card-impresso") {
        const attach = document.getElementById("attach-label");
        if (attach) {
          attach.style.pointerEvents = enabled ? "auto" : "none";
          attach.style.opacity = enabled ? "1" : ".6";
        }
        const file = document.getElementById("layout_file");
        if (file) file.disabled = !enabled;
      }
    }

    function applyCheckboxStates() {
      const cfg = [
        { key: 'impresso',      flag: 'impresso_flag',      card: 'card-impresso' },
        { key: 'fita',          flag: 'fita_flag',          card: 'card-fita' },
        { key: 'resistencia',   flag: 'resistencia_flag',   card: 'card-resistencia' },
  // Transparência estava incorretamente apontando para 'card-tratamento' (tratamento dinas),
  // o que impedia o disable visual e funcional do campo de transparência.
  // Ajustado para 'card-transparencia'.
  { key: 'transparencia', flag: 'transparencia_flag', card: 'card-transparencia' },
        { key: 'tratamento',    flag: 'tratamento_flag',    card: 'card-tratamento', extra: 'tratamento_dinas_visible' },
        { key: 'vendido',       flag: 'vendido_flag' }
      ];
      cfg.forEach(c => {
        const cb = document.querySelector(`input[data-toggle='${c.key}']`);
        if (!cb) return;
        const checked = cb.checked;
        const flag = document.getElementById(c.flag);
        if (flag) flag.value = checked ? '1' : '0';
        if (c.card && c.key !== 'tratamento') setCardEnabled(c.card, checked);
        if (c.key === 'tratamento') {
          const input = document.getElementById(c.extra);
          const cardTrat = document.getElementById('card-tratamento');
          if (input) {
            input.disabled = !checked;
            if (!checked) input.value='';
          }
            if (cardTrat) cardTrat.classList.toggle('is-off', !checked);
        }
      });
      // Cliente obrigatório somente se vendido
      const vendidoOn = document.querySelector("input[data-toggle='vendido']")?.checked;
      const clienteSelect = document.getElementById('cliente_id');
      const asterisk = document.getElementById('cliente-required-asterisk');
      const clienteRow = document.getElementById('row-cliente');
      if (clienteSelect && !IS_VIEW) {
        if (vendidoOn) {
          clienteSelect.disabled = false;
          clienteSelect.classList.remove('is-off');
          clienteSelect.setAttribute('required','required');
          if (clienteRow) clienteRow.classList.remove('is-off');
          if (asterisk) asterisk.style.visibility = 'visible';
        } else {
          clienteSelect.removeAttribute('required');
          clienteSelect.value = '';
          clienteSelect.disabled = true;
          if (clienteRow) clienteRow.classList.add('is-off');
          if (asterisk) asterisk.style.visibility = 'hidden';
        }
      }
    }

    function bindCheckboxToggles() {
      document.querySelectorAll('#emb-togglebar input[type=checkbox][data-toggle]').forEach(cb => {
        cb.addEventListener('change', () => {
          applyCheckboxStates();
        });
      });
      applyCheckboxStates();
    }

    /* -------- NCM helpers -------- */
    const NCM = {
      ui: { input: null, menu: null, form: null },
      searchDebounced: null,

      init(form) {
        this.ui.form  = form;
        this.ui.input = form.querySelector("#ncm");
        this.ui.menu  = form.querySelector("#ncm-menu");
        if (!this.ui.input) return;

        // Máscara com pontuação 0000.00.00
        Util.attachMask(this.ui.input, Util.formatNCM);

        // Sugestão silenciosa do servidor
        const suggest = (form.getAttribute("data-suggest-ncm") || "").trim();
        if (!this.ui.input.value && /^\d{8}$/.test(suggest)) {
          this.ui.input.value = Util.formatNCM(suggest);
          this.fetchHint(suggest);
        }

        // Se estiver editando com valor, descreve
        const d0 = Util.onlyDigits(this.ui.input.value);
        if (/^\d{8}$/.test(d0)) this.fetchHint(d0);

        // Autocomplete
        this.searchDebounced = Util.debounce((term) => this.search(term), 220);

        // Eventos
        this.ui.input.addEventListener("input", () => this.onInput());

        // Validação leve
        form.addEventListener("submit", (ev) => {
          const d = Util.onlyDigits(this.ui.input.value);
          if (d && d.length !== 8) {
            ev.preventDefault();
            App.Notice.show("NCM deve ter exatamente 8 dígitos.", { type: "error" });
            this.ui.input.focus();
          }
        });
      },

      onInput() {
        const d = Util.onlyDigits(this.ui.input.value || "");
        if (d.length === 8) this.fetchHint(d);
        if (d.length >= 4) this.searchDebounced(d);
        else if (this.ui.menu) this.ui.menu.hidden = true;
      },

      async fetchHint(code8) {
        if (!/^\d{8}$/.test(code8)) return;
        try {
          const r = await fetch(`/api/ncm/${code8}`);
          const data = await r.json().catch(() => null);
          if (r.ok && data && data.ok) {
            App.Notice.show(`${data.codigo} — ${data.descricao}`, { type: "success", timeout: 3000 });
          } else if (r.status === 404) {
            App.Notice.show("NCM não encontrado na base.", { type: "warn" });
          } else if (r.status === 503) {
            App.Notice.show("Tabela NCM não instalada no sistema.", { type: "warn" });
          }
        } catch (e) {
          console.error(e);
          App.Notice.show("Falha ao consultar NCM.", { type: "error" });
        }
      },

      async search(termRaw) {
        const t = String(termRaw || "").trim();
        if (!t) return;
        try {
          const qs = encodeURIComponent(t);
          const r = await fetch(`/api/ncm?q=${qs}`);
          if (!r.ok) return;
          const rows = (await r.json()) || [];
          this.renderMenu(rows);
          if (rows.length) Pop.open(this.ui.menu, this.ui.input);
          else this.ui.menu.hidden = true;
        } catch (e) {
          console.error(e);
          this.ui.menu.hidden = true;
        }
      },

      renderMenu(rows) {
        if (!this.ui.menu) return;
        const list = Array.isArray(rows) ? rows : [];
        if (!list.length) {
          this.ui.menu.innerHTML = `<div class="menu-empty">Nenhum resultado.</div>`;
          return;
        }
        this.ui.menu.innerHTML = "";
        list.forEach((r) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "menu-item";
          btn.innerHTML = `<span class="mono">${r.codigo}</span> <span class="ellipsis">${
            String(r.descricao || "").replace(/</g, "&lt;").replace(/>/g, "&gt;")
          }</span>`;
          btn.addEventListener("click", () => {
            this.ui.input.value = Util.formatNCM(r.codigo);
            this.fetchHint(r.codigo);
            Pop.closeAll();
          });
          this.ui.menu.appendChild(btn);
        });
        Util.icones();
      },
    };

    function init() {
      const form = document.getElementById("embalagens-form");
      if (!form) return;

      const tb = document.getElementById("emb-togglebar");
      if (!tb) return;
      IS_VIEW = tb.getAttribute('aria-disabled') === 'true';
      bindCheckboxToggles();

      const file = document.getElementById("layout_file");
      if (file) {
        file.addEventListener("change", () => {
          const input = document.getElementById("layout_png");
          if (file.files && file.files[0] && input) {
            input.value = file.files[0].name;
          }
        });
      }

  // Nenhuma sync adicional extra necessária além da atualização dos flags

      // Inicializa NCM
      NCM.init(form);

      App.Util.icones();
    }

    return { init };
  })();

  /* ===========================
   * Auto-init
   * =========================== */
  document.addEventListener("DOMContentLoaded", () => {
    App.Notice.init();
    App.Forms.applyMasksIfAny();

    // inicializa módulos por presença do container
    if (document.getElementById("clientes-list")) App.Clientes.init();
    if (document.getElementById("colaboradores-list")) App.Colaboradores.init();
    if (document.getElementById("embalagens-form")) App.EmbalagensForm.init();
    if (document.getElementById("pedidos-list")) App.Pedidos.init?.();
  });
})(window, document);
/* ===========================
 * Página: Impressão (impressoes.html)
 * =========================== */
App.Impressao = (function () {
  const ui = {};
  const state = { data: [] };
  
  async function popularFiltros() {
    // Popular clientes
    const clienteSel = document.getElementById('filtro-cliente');
    if (clienteSel) {
      try {
        const r = await fetch('/api/clientes');
        const rows = await r.json();
        clienteSel.innerHTML = '<option value="">Cliente</option>' + rows.map(c => `<option value="${c.id}">${c.codigo_interno || ''} - ${c.razao_social}</option>`).join('');
      } catch (e) { clienteSel.innerHTML = '<option value="">Cliente</option>'; }
    }
    // Popular parceiros
    const parceiroSel = document.getElementById('filtro-fornecedor');
    if (parceiroSel) {
      try {
        const r = await fetch('/api/parceiros');
        const rows = await r.json();
        parceiroSel.innerHTML = '<option value="">Fornecedor</option>' + rows.map(p => `<option value="${p.id}">${p.nome}</option>`).join('');
        parceiroSel.style.display = 'inline-block';
      } catch (e) { parceiroSel.innerHTML = '<option value="">Fornecedor</option>'; }
    }
    // Popular máquinas
    const maquinaSel = document.getElementById('filtro-maquina');
    if (maquinaSel) {
      try {
        const r = await fetch('/api/maquinas');
        const rows = await r.json();
        maquinaSel.innerHTML = '<option value="">Máquina</option>' + rows.map(m => `<option value="${m.id}">${m.nome}</option>`).join('');
        maquinaSel.style.display = 'inline-block';
      } catch (e) { maquinaSel.innerHTML = '<option value="">Máquina</option>'; }
    }
  }

  function grabUI() {
    ui.list = document.getElementById('impressoes-list');
    ui.scrollWrap = document.getElementById('impressoes-scroll-container');
    ui.empty = document.getElementById('impressoes-sem-dados');
    ui.error = document.getElementById('impressoes-list-error');
    ui.busca = document.getElementById('busca-impressoes');
    ui.selStatus = document.getElementById('filtro-status');
    ui.selExecucao = document.getElementById('filtro-execucao');
    ui.selCliente = document.getElementById('filtro-cliente');
    ui.selFornecedor = document.getElementById('filtro-fornecedor');
    ui.selMaquina = document.getElementById('filtro-maquina');
    ui.dataInicio = document.getElementById('filtro-data-inicio');
    ui.dataFim = document.getElementById('filtro-data-fim');
    ui.btnExportCSV = document.getElementById('btn-export-csv');
    ui.btnNovaOI = document.getElementById('btn-adicionar-oi');
    ui.btnReload = document.getElementById('btn-reload-impressoes');
    ui.subtitle = document.getElementById('impressoes-subtitle');
  }

  function bindEvents() {
    ui.busca?.addEventListener('input', App.Util.debounce(fetchList, 350));
    ui.selStatus?.addEventListener('change', fetchList);
    ui.selExecucao?.addEventListener('change', fetchList);
    ui.selCliente?.addEventListener('change', fetchList);
    ui.selFornecedor?.addEventListener('change', fetchList);
    ui.selMaquina?.addEventListener('change', fetchList);
    ui.dataInicio?.addEventListener('change', fetchList);
    ui.dataFim?.addEventListener('change', fetchList);
    ui.btnReload?.addEventListener('click', fetchList);
    ui.btnNovaOI?.addEventListener('click', () => {
      // TODO: Implementar criação de nova OI
      alert('Funcionalidade em desenvolvimento');
    });
    ui.btnExportCSV?.addEventListener('click', () => {
      // TODO: Implementar exportação CSV
      alert('Funcionalidade em desenvolvimento');
    });
  }

  function buildQuery() {
    const params = new URLSearchParams();
    const q = (ui.busca?.value || '').trim(); if (q) params.set('q', q);
    const st = ui.selStatus?.value; if (st) params.set('status', st);
    const ex = ui.selExecucao?.value; if (ex) params.set('execucao', ex);
    const cl = ui.selCliente?.value; if (cl) params.set('cliente_id', cl);
    const fo = ui.selFornecedor?.value; if (fo) params.set('fornecedor_id', fo);
    const mq = ui.selMaquina?.value; if (mq) params.set('maquina_id', mq);
    const di = ui.dataInicio?.value; if (di) params.set('data_inicio', di);
    const df = ui.dataFim?.value; if (df) params.set('data_fim', df);
    return params.toString();
  }

  let currentFetchSeq = 0; // sequenciador para descartar respostas antigas
  async function fetchList() {
    if (!ui.list) return;
    const mySeq = ++currentFetchSeq;
    const qs = buildQuery();
    // Sinaliza loading
    if (ui.scrollWrap) ui.scrollWrap.dataset.loading = '1';
    if (ui.empty) ui.empty.hidden = true;
    if (ui.error) ui.error.hidden = true;
    
    try {
      // TODO: Quando a API estiver pronta, substituir por chamada real
      // const r = await fetch('/api/impressao/ordens' + (qs ? `?${qs}` : ''));
      // const rows = await r.json();
      
      // Mock de dados temporário
      await new Promise(r => setTimeout(r, 500)); // simula delay de rede
      const rows = [
        {id: 1, numero: 'OI-001', cliente: 'Cliente ABC', arte: 'Arte 123', execucao: 'INTERNA', fornecedor: '-', maquina: 'M1', cores: '4', data_prevista: '2025-10-05', metragem: '1000', status: 'ABERTA'},
        {id: 2, numero: 'OI-002', cliente: 'Cliente XYZ', arte: 'Logo Principal', execucao: 'TERCEIRO', fornecedor: 'Gráfica Express', maquina: '-', cores: '6', data_prevista: '2025-10-15', metragem: '2500', status: 'ENVIADA_AO_TERCEIRO'},
        {id: 3, numero: 'OI-003', cliente: 'Empresa 123', arte: 'Embalagem V2', execucao: 'INTERNA', fornecedor: '-', maquina: 'M3', cores: '2', data_prevista: '2025-09-30', metragem: '800', status: 'CONCLUIDA'}
      ];
      
      if (mySeq !== currentFetchSeq) return; // resposta obsoleta
      state.data = Array.isArray(rows) ? rows : [];
      renderList();
    } catch (err) {
      if (mySeq !== currentFetchSeq) return;
      console.error('Erro ao carregar OIs:', err);
      if (ui.error) {
        ui.error.hidden = false;
        ui.list.innerHTML = '';
      }
    } finally {
      if (ui.scrollWrap && mySeq === currentFetchSeq) {
        requestAnimationFrame(() => {
          delete ui.scrollWrap.dataset.loading;
        });
      }
    }
  }

  function renderList() {
    if (!ui.list) return;
    // preserva primeira criança (header) se existir
    const header = ui.list.querySelector('.impresso-card.header');
    ui.list.innerHTML = '';
    if (header) ui.list.appendChild(header);

    const total = state.data.length;
    if (ui.subtitle) ui.subtitle.textContent = total ? `${total} OI${total>1?'s':''}` : '';

    if (!total) {
      if (ui.empty) ui.empty.hidden = false;
      return;
    } else if (ui.empty) ui.empty.hidden = true;

    const frag = document.createDocumentFragment();
    state.data.forEach(oi => frag.appendChild(criaLinhaOI(oi)));
    ui.list.appendChild(frag);
    App?.Util?.icones?.();
  }

  function criaLinhaOI(oi) {
    const d = document.createElement('div');
    d.className = 'impresso-card';
    d.setAttribute('role', 'listitem');
    d.dataset.oid = oi.id;

    // Formata os campos
    const numero = oi.numero || '—';
    const cliente = oi.cliente || '—';
    const arte = oi.arte || '—';
    const execucao = oi.execucao || '—';
    const fornecedor_maquina = oi.execucao === 'TERCEIRO' ? (oi.fornecedor || '—') : (oi.maquina || '—');
    const cores = oi.cores || '—';
    const data_prevista = formatarData(oi.data_prevista) || '—';
    const metragem = oi.metragem ? `${oi.metragem} m` : '—';
    const status = oi.status || 'ABERTA';
    const statusClass = 'status-chip is-'+status.toLowerCase().replace(/_/g,'-');
    const statusLabel = formatarStatus(status);

    // Montagem da linha
    d.innerHTML = `
      <div class="cell numero" title="${numero}">${numero}</div>
      <div class="cell cliente" title="${cliente}">${escapeHtml(cliente)}</div>
      <div class="cell arte" title="${arte}">${escapeHtml(arte)}</div>
      <div class="cell execucao" title="${execucao}">${execucao}</div>
      <div class="cell fornecedor_maquina" title="${fornecedor_maquina}">${escapeHtml(fornecedor_maquina)}</div>
      <div class="cell cores" title="${cores}">${cores}</div>
      <div class="cell data_prevista" title="${data_prevista}">${data_prevista}</div>
      <div class="cell metragem" title="${metragem}">${metragem}</div>
      <div class="cell status" title="${statusLabel}"><span class="${statusClass}">${statusLabel}</span></div>`;
    return d;
  }

  function formatarData(isoDate) {
    if (!isoDate) return '';
    const s = String(isoDate).slice(0, 10); // yyyy-mm-dd
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
    if (!m) return isoDate;
    return `${m[3]}/${m[2]}/${m[1].slice(2)}`; // DD/MM/YY
  }

  function formatarStatus(status) {
    if (!status) return '—';
    return status.replace(/_/g, ' ').toLowerCase().replace(/(^|\s)\S/g, c => c.toUpperCase());
  }

  function escapeHtml(s) {
    return String(s || '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  async function init() {
    grabUI();
    if (!ui.list) return; // não está na página de impressões
    
    await popularFiltros();
    bindEvents();
    fetchList();
  }

  return { init };
})();
