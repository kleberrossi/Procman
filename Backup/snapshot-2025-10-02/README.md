Snapshot: 2025-10-02
=================================
Escopo:
- Captura do estado atual da UI de Pedidos após migração para barra flutuante única de ações.
- Remoção completa de fades (gradientes) de overflow horizontal e lógica associada.
- Compactação dos botões de ação (26px) e deslocamento horizontal configurável via variáveis CSS (--pedido-float-right / --pedido-float-btn).

Principais Alterações Resumidas:
1. Floating Action Bar (#pedido-actions-float) substitui overlays por linha.
2. Código de fades e referências 'fades-ready' removidos de JS/CSS.
3. Template pedidos.html sem elementos .overflow-fade.
4. Variáveis CSS introduzidas para facilitar ajustes futuros de posição e tamanho.

Arquivos Incluídos:
- static/js/app.js (snapshot lógico abreviado nas cópias reduzidas locais se desejado; usar original em produção).
- static/css/modern-style.css (estado completo no momento do snapshot; contém bloco da floating bar).
- templates/pedidos.html (sem fades, header intacto).

Restauraçao:
Copiar os arquivos deste diretório de volta para seus caminhos originais sobrescrevendo.

Notas Futuras:
- Realizar limpeza adicional de comentários legacy de ações por linha, se necessário.
- Considerar acessibilidade adicional (ARIA) para a barra flutuante.

Criado automaticamente.