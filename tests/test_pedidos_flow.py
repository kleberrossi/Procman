def test_criar_pedido_e_codigo_sequencial(app_client):
    # cria primeiro cliente para vincular
    resp = app_client.post('/api/clientes', json={
        'razao_social':'Cliente A', 'cnpj':'12345678000191'
    })
    assert resp.status_code == 201
    cliente_id = resp.get_json()['id']

    # cria pedido
    p1 = app_client.post('/api/pedidos', json={'cliente_id': cliente_id}).get_json()
    assert p1['numero_pedido'].startswith('PED-')

    # cria segundo
    p2 = app_client.post('/api/pedidos', json={'cliente_id': cliente_id}).get_json()
    n1 = int(p1['numero_pedido'].split('-')[1])
    n2 = int(p2['numero_pedido'].split('-')[1])
    assert n2 == n1 + 1


def test_transicao_invalida_status(app_client):
    c = app_client.post('/api/clientes', json={'razao_social':'Cliente B','cnpj':'22345678000191'}).get_json()
    ped = app_client.post('/api/pedidos', json={'cliente_id': c['id']}).get_json()
    # tentar pular direto para CONCLUIDO
    resp = app_client.post(f"/api/pedidos/{ped['id']}/status", json={'status':'CONCLUIDO'})
    assert resp.status_code == 400


def test_snapshot_immutavel_apos_aprovado(app_client):
    c = app_client.post('/api/clientes', json={'razao_social':'Cliente C','cnpj':'32345678000191'}).get_json()
    ped = app_client.post('/api/pedidos', json={'cliente_id': c['id']}).get_json()
    # criar embalagem p/ item
    app_client.post('/api/embalagens', json={
        'embalagem_code':'EMB001','cliente_id':c['id'],'material':'PE','sanfona_mm':0,'aba_mm':0
    })
    resp_item = app_client.post(f"/api/pedidos/{ped['id']}/itens", json={'embalagem_code':'EMB001','rev':'R00','qtd':10,'preco_unit':2.5})
    assert resp_item.status_code == 201, resp_item.get_data(as_text=True)
    it = resp_item.get_json()
    # aprovar pedido
    app_client.post(f"/api/pedidos/{ped['id']}/status", json={'status':'APROVADO'})
    # tentar alterar snapshot_material via PATCH
    resp = app_client.patch(f"/api/pedidos/{ped['id']}/itens/{it['id']}", json={'snapshot_material':'OUTRO','status_impressao':'pendente'})
    j = resp.get_json()
    # snapshot_material não deve mudar (permanece material original 'PE')
    assert j.get('snapshot_material') == 'PE'
    # garantir que status_impressao atualizou
    it2 = app_client.patch(f"/api/pedidos/{ped['id']}/itens/{it['id']}", json={'status_impressao':'concluida'}).get_json()
    assert it2['status_impressao'] == 'concluida'


def test_auto_execucao_primeira_ordem(app_client):
    c = app_client.post('/api/clientes', json={'razao_social':'Cliente D','cnpj':'42345678000191'}).get_json()
    ped = app_client.post('/api/pedidos', json={'cliente_id': c['id']}).get_json()
    app_client.post(f"/api/pedidos/{ped['id']}/status", json={'status':'APROVADO'})
    # criar ordem
    op = app_client.post(f"/api/pedidos/{ped['id']}/ordens_producao", json={'largura_mm':100}).get_json()
    assert op['id']
    # buscar pedido para validar status
    # (endpoint detail)
    ped_detail = app_client.get(f"/api/pedidos/{ped['id']}").get_json()['pedido']
    assert ped_detail['status'] == 'EM_EXECUCAO'


def test_metrics_basico(app_client):
    c = app_client.post('/api/clientes', json={'razao_social':'Cliente E','cnpj':'52345678000191'}).get_json()
    ped = app_client.post('/api/pedidos', json={'cliente_id': c['id']}).get_json()
    app_client.post('/api/embalagens', json={'embalagem_code':'EMB002','cliente_id':c['id'],'material':'PE','sanfona_mm':0,'aba_mm':0})
    resp_item2 = app_client.post(f"/api/pedidos/{ped['id']}/itens", json={'embalagem_code':'EMB002','rev':'R00','qtd':5,'preco_unit':3.0,'peso_unit_kg':0.02})
    assert resp_item2.status_code == 201, resp_item2.get_data(as_text=True)
    metrics = app_client.get(f"/api/pedidos/{ped['id']}/metrics").get_json()
    assert metrics['total_itens'] == 1
    assert metrics['valor_total_calc'] == 15.0
