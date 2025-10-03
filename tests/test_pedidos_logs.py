import json

# Objetivo: validar ordem e tipos de logs gerados no ciclo principal
# Ações: criar pedido, adicionar item, aprovar, criar OP, patch status_impressao
# Esperados (subconjunto e ordem relativa): CREATED, ITEM_ADDED, STATUS_CHANGED (RASCUNHO->APROVADO), OP_CREATED, ITEM_UPDATED


def test_pedido_logs_fluxo_basico(app_client):
    # cliente
    c = app_client.post('/api/clientes', json={'razao_social':'Cliente Logs','cnpj':'90111111000191'}).get_json()
    # pedido
    p = app_client.post('/api/pedidos', json={'cliente_id': c['id']}).get_json()
    pedido_id = p['id']
    # embalagem
    app_client.post('/api/embalagens', json={
        'embalagem_code':'EMB_LOG','cliente_id':c['id'],'material':'PE','sanfona_mm':0,'aba_mm':0,'rev':'R00'
    })
    # item
    it_resp = app_client.post(f"/api/pedidos/{pedido_id}/itens", json={'embalagem_code':'EMB_LOG','rev':'R00','qtd':2,'preco_unit':3.5})
    assert it_resp.status_code == 201
    item = it_resp.get_json()
    # aprovar
    app_client.post(f"/api/pedidos/{pedido_id}/status", json={'status':'APROVADO'})
    # criar OP
    app_client.post(f"/api/pedidos/{pedido_id}/ordens_producao", json={'largura_mm':150})
    # patch item (status impressao)
    app_client.patch(f"/api/pedidos/{pedido_id}/itens/{item['id']}", json={'status_impressao':'pendente'})

    # buscar logs
    logs = app_client.get(f"/api/pedidos/{pedido_id}/logs").get_json()
    tipos = [l['acao'] for l in logs]

    # Verificações essenciais
    assert 'CREATED' in tipos
    assert 'ITEM_ADDED' in tipos
    assert 'STATUS_CHANGED' in tipos
    assert 'OP_CREATED' in tipos
    assert 'ITEM_UPDATED' in tipos

    # Ordem relativa: CREATED antes de ITEM_ADDED; ITEM_ADDED antes de STATUS_CHANGED; STATUS_CHANGED antes de OP_CREATED
    def idx(a):
        return tipos.index(a)
    assert idx('CREATED') < idx('ITEM_ADDED')
    assert idx('ITEM_ADDED') < idx('STATUS_CHANGED')
    assert idx('STATUS_CHANGED') < idx('OP_CREATED')
