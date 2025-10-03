Clean Snapshot 2025-10-02 ( pós-refatoração )
================================================
Objetivo
- Versão consolidada SEM overlays por linha e SEM fades.
- Barra flutuante única (toolbar) com acessibilidade (role=toolbar + navegação por setas).
- Código JS refatorado: removidos vestígios de positionActionOverlays / fades-ready.

Componentes-Chave
- Pedidos: cálculo de colunas congeladas -> expansão -> reposicionamento da barra via repositionFloatBar().
- Floating Bar: centraliza verticalmente no card hovered; teclas ← → Home End ciclam foco.
- Variáveis CSS: --pedido-float-right / --pedido-float-btn para ajuste rápido.

Arquivos neste snapshot são placeholders resumidos; usar diretórios de produção para conteúdo integral.

Como restaurar comportamento
1. Copiar template `templates/pedidos.html` deste snapshot (remoção de fades já aplicada).
2. Garantir que CSS não contenha blocos de `.pedido-actions` ou `.overflow-fade` (já removidos no principal).
3. Confirmar que JS não chama mais `positionActionOverlays()` (substituído por `repositionFloatBar`).

Próximos Passos Sugeridos
- (Opcional) Gerar testes de UI (Playwright ou Cypress) validando:
  * Barra aparece ao mover mouse sobre linha.
  * Foco de teclado navega entre botões.
- (Opcional) Adicionar botão de "pin" para manter barra fixa num pedido selecionado.
- (Opcional) Persistir última largura congelada em localStorage (micro cachê de layout).

Fim.
