// Configuração do popup menu para pedidos (versão com menu contextual)
// Backup salvo em: pedidos_popup_version.html

App.Pedidos = (function(){
  'use strict';
  const state = { data: [], logs: [] };
  const ui = {};

  function grabListUI(){
    ui.list = document.getElementById('pedidos-list');
    ui.popup = document.getElementById('pedidos-popup-menu');
    ui.empty = document.getElementById('pedidos-sem-dados');
    ui.busca = document.getElementById('busca-pedidos');
    ui.selStatus = document.getElementById('filtro-status');
    ui.selRep = document.getElementById('filtro-rep');
    ui.btnFiltrar = document.getElementById('btn-filtrar-pedidos');
    ui.btnRefresh = document.getElementById('btn-refresh-pedidos');
  }

  function rowEl(p){
    const d = document.createElement('div');
    d.className = 'pedido-row';
    
    // Preparar dados com fallbacks
    const codigo = p.numero_pedido || '—';
    const venda = p.tipo_venda || '—';
    const comissao = p.comissao_percent ? `${p.comissao_percent}%` : '—';
    const repr = p.representante_nome || (p.representante_id ? ('#'+p.representante_id) : '—');
    const cliente = p.cliente_nome || '—';
    const descricao = p.descricao_embalagem || '—';
    const preco = p.preco_total != null ? fmtMoney(p.preco_total) : '—';
    const precoKg = p.preco_kg ? fmtMoney(p.preco_kg) : '—';
    const material = p.material || '—';
    const anel = p.anel || '—';
    const comImpressao = p.com_impressao ? 'Sim' : 'Não';
    const pesoUnit = p.peso_unitario ? `${p.peso_unitario} kg` : '—';
    const qtdExtrusar = p.qtd_extrusar ? `${p.qtd_extrusar} kg` : '—';
    const extrusado = p.extrusado ? 'Sim' : 'Não';
    const qtdExtrusada = p.qtd_extrusada ? `${p.qtd_extrusada} kg` : '—';
    const statusImp = p.status_impressao || '—';

    d.innerHTML = `
      <div title="${codigo}">${codigo}</div>
      <div title="${venda}">${venda}</div>
      <div class="valor" title="${comissao}">${comissao}</div>
      <div title="${repr}">${repr}</div>
      <div title="${cliente}">${cliente}</div>
      <div title="${descricao}">${descricao}</div>
      <div class="preco" title="${preco}">${preco}</div>
      <div class="preco" title="${precoKg}">${precoKg}</div>
      <div title="${material}">${material}</div>
      <div title="${anel}">${anel}</div>
      <div class="boolean">
        <span class="status-badge ${comImpressao === 'Sim' ? 'com-impressao' : 'sem-impressao'}">${comImpressao}</span>
      </div>
      <div title="${pesoUnit}">${pesoUnit}</div>
      <div title="${qtdExtrusar}">${qtdExtrusar}</div>
      <div class="boolean">
        <span class="status-badge ${extrusado === 'Sim' ? 'extrusado' : 'nao-extrusado'}">${extrusado}</span>
      </div>
      <div title="${qtdExtrusada}">${qtdExtrusada}</div>
      <div class="boolean">
        <span class="status-badge">${statusImp}</span>
      </div>
    `;
    return d;
  }

  function showPopupMenu(event, pedidoId) {
    event.preventDefault();
    event.stopPropagation();
    
    if (!ui.popup) return;
    
    // Encontra os dados do pedido
    const pedido = state.data.find(p => String(p.id) === String(pedidoId));
    if (!pedido) return;
    
    // Atualiza o popup com o ID do pedido
    ui.popup.dataset.pedidoId = pedidoId;
    
    // Posiciona o popup próximo ao clique
    const rect = event.currentTarget.getBoundingClientRect();
    const popupRect = ui.popup.getBoundingClientRect();
    
    let left = event.clientX + 10;
    let top = event.clientY + 10;
    
    // Ajusta posição se sair da tela
    if (left + 140 > window.innerWidth) {
      left = event.clientX - 150;
    }
    if (top + 120 > window.innerHeight) {
      top = event.clientY - 130;
    }
    
    ui.popup.style.left = `${left}px`;
    ui.popup.style.top = `${top}px`;
    ui.popup.hidden = false;
  }

  function hidePopupMenu() {
    if (ui.popup) {
      ui.popup.hidden = true;
      ui.popup.removeAttribute('data-pedido-id');
    }
  }

  function bindListEvents(){
    if (!ui.list || !ui.popup) return;
    
    const debounced = App.Util.debounce(()=>fetchList(), 350);
    ui.busca?.addEventListener('input', debounced);
    ui.selStatus?.addEventListener('change', fetchList);
    ui.selRep?.addEventListener('change', fetchList);
    ui.btnFiltrar?.addEventListener('click', fetchList);
    ui.btnRefresh?.addEventListener('click', fetchList);
    
    // Eventos para mostrar popup ao clicar nas linhas
    ui.list.addEventListener('click', (e) => {
      const row = e.target.closest('.pedido-row');
      if (!row) return;
      
      const pedidoId = row.dataset.pedidoId;
      if (pedidoId) {
        showPopupMenu(e, pedidoId);
      }
    });
    
    // Eventos do popup menu
    ui.popup.addEventListener('click', async (e) => {
      const button = e.target.closest('.popup-menu-item');
      if (!button) return;
      
      const action = button.dataset.action;
      const pedidoId = ui.popup.dataset.pedidoId;
      
      if (!pedidoId) return;
      
      hidePopupMenu();
      
      switch (action) {
        case 'view':
          window.location.href = `/pedidos/${pedidoId}`;
          break;
        case 'edit':
          window.location.href = `/pedidos/${pedidoId}/editar`;
          break;
        case 'delete':
          if (!confirm('Excluir pedido?')) return;
          try {
            const resp = await fetch(`/api/pedidos/${pedidoId}`, { method: 'DELETE' });
            if (resp.status === 204) {
              state.data = state.data.filter(p => String(p.id) !== String(pedidoId));
              renderList();
            } else {
              const err = await resp.json().catch(() => ({}));
              App.Notice.show(err.error || 'Falha ao excluir', { type: 'error' });
            }
          } catch (_) {
            App.Notice.show('Erro de rede', { type: 'error' });
          }
          break;
      }
    });
    
    // Esconder popup ao clicar fora
    document.addEventListener('click', (e) => {
      if (ui.popup && !ui.popup.contains(e.target) && !ui.list.contains(e.target)) {
        hidePopupMenu();
      }
    });
    
    // Esconder popup ao pressionar Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        hidePopupMenu();
      }
    });
  }

  function renderList(){
    if (!ui.list) return;
    ui.list.innerHTML = '';
    
    if (!state.data.length){
      if (ui.empty) ui.empty.hidden = false;
      return;
    } else if (ui.empty) ui.empty.hidden = true;
    
    const listFrag = document.createDocumentFragment();
    
    state.data.forEach(p => {
      const row = rowEl(p);
      row.dataset.pedidoId = p.id;
      listFrag.appendChild(row);
    });
    
    ui.list.appendChild(listFrag);
    App.Util.icones();
  }

  // ...resto das funções...
})();