import re

def _novo_cliente(client, razao, cnpj):
    return client.post('/api/clientes', json={'razao_social':razao,'cnpj':cnpj}).get_json()

def _novo_pedido(client, cliente_id):
    return client.post('/api/pedidos', json={'cliente_id': cliente_id}).get_json()

def _nova_emb(client, cod, cliente_id, rev='R00'):
    return client.post('/api/embalagens', json={'embalagem_code':cod,'cliente_id':cliente_id,'material':'PE','sanfona_mm':0,'aba_mm':0,'rev':rev}).get_json()

def _add_item(client, pedido_id, cod, rev='R00', **extra):
    payload={'embalagem_code':cod,'rev':rev,'qtd':extra.get('qtd',5),'preco_unit':extra.get('preco_unit',2.0)}
    return client.post(f'/api/pedidos/{pedido_id}/itens', json=payload)


def test_status_flow_completo(app_client):
    c = _novo_cliente(app_client,'Cliente Flow','11111111000191')
    p = _novo_pedido(app_client, c['id'])
    assert p['status'] == 'RASCUNHO'
    # aprova
    r = app_client.post(f"/api/pedidos/{p['id']}/status", json={'status':'APROVADO'})
    assert r.status_code == 200
    # cria OP -> muda para EM_EXECUCAO
    r2 = app_client.post(f"/api/pedidos/{p['id']}/ordens_producao", json={'largura_mm':100})
    assert r2.status_code in (200,201)
    p2 = app_client.get(f"/api/pedidos/{p['id']}").get_json()['pedido']
    assert p2['status'] == 'EM_EXECUCAO'
    # conclui
    r3 = app_client.post(f"/api/pedidos/{p['id']}/status", json={'status':'CONCLUIDO'})
    assert r3.status_code == 200
    p3 = app_client.get(f"/api/pedidos/{p['id']}").get_json()['pedido']
    assert p3['status'] == 'CONCLUIDO'


def test_add_item_bloqueado_apos_aprovado(app_client):
    c = _novo_cliente(app_client,'Cliente AddBlock','21111111000191')
    p = _novo_pedido(app_client, c['id'])
    _nova_emb(app_client,'EMB10', c['id'])
    # adiciona em rascunho
    r1 = _add_item(app_client, p['id'],'EMB10')
    assert r1.status_code == 201
    # aprova
    app_client.post(f"/api/pedidos/{p['id']}/status", json={'status':'APROVADO'})
    # tenta novo item
    r2 = _add_item(app_client, p['id'],'EMB10')
    assert r2.status_code == 400


def test_patch_restrito_pos_aprovado(app_client):
    c = _novo_cliente(app_client,'Cliente Patch','31111111000191')
    p = _novo_pedido(app_client, c['id'])
    _nova_emb(app_client,'EMB11', c['id'])
    item_resp = _add_item(app_client, p['id'],'EMB11')
    item = item_resp.get_json()
    app_client.post(f"/api/pedidos/{p['id']}/status", json={'status':'APROVADO'})
    # tentar mudar qtd (forbidden)
    r_forb = app_client.patch(f"/api/pedidos/{p['id']}/itens/{item['id']}", json={'qtd':999})
    assert r_forb.status_code == 400
    # mudar status_impressao (permitido)
    r_ok = app_client.patch(f"/api/pedidos/{p['id']}/itens/{item['id']}", json={'status_impressao':'pendente'})
    assert r_ok.status_code == 200
    assert r_ok.get_json()['status_impressao'] == 'pendente'


def test_delete_item_bloqueado_apos_aprovado(app_client):
    c = _novo_cliente(app_client,'Cliente DelBlock','41111111000191')
    p = _novo_pedido(app_client, c['id'])
    _nova_emb(app_client,'EMB12', c['id'])
    item = _add_item(app_client, p['id'],'EMB12').get_json()
    app_client.post(f"/api/pedidos/{p['id']}/status", json={'status':'APROVADO'})
    rdel = app_client.delete(f"/api/pedidos/{p['id']}/itens/{item['id']}")
    assert rdel.status_code == 400


def test_recalculo_total_delete(app_client):
    c = _novo_cliente(app_client,'Cliente Recalc','51111111000191')
    p = _novo_pedido(app_client, c['id'])
    _nova_emb(app_client,'EMB13', c['id'])
    i1 = _add_item(app_client, p['id'],'EMB13')
    i2 = _add_item(app_client, p['id'],'EMB13', qtd=3, preco_unit=4.0)
    assert i1.status_code == 201 and i2.status_code == 201
    # total esperado = 5*2 + 3*4 = 10 +12 =22
    metrics = app_client.get(f"/api/pedidos/{p['id']}/metrics").get_json()
    assert metrics['valor_total_calc'] == 22.0
    # deletar primeiro item (RASCUNHO ainda)
    item_json = i1.get_json()
    rdel = app_client.delete(f"/api/pedidos/{p['id']}/itens/{item_json['id']}")
    assert rdel.status_code == 204
    metrics2 = app_client.get(f"/api/pedidos/{p['id']}/metrics").get_json()
    assert metrics2['valor_total_calc'] == 12.0


def test_metrics_multi_itens(app_client):
    c = _novo_cliente(app_client,'Cliente Metrics2','61111111000191')
    p = _novo_pedido(app_client, c['id'])
    _nova_emb(app_client,'EMB14', c['id'])
    _add_item(app_client, p['id'],'EMB14', qtd=2, preco_unit=5.0)
    _add_item(app_client, p['id'],'EMB14', qtd=4, preco_unit=1.5)
    metrics = app_client.get(f"/api/pedidos/{p['id']}/metrics").get_json()
    # total = 2*5 + 4*1.5 = 10 + 6 = 16
    assert metrics['valor_total_calc'] == 16.0
    assert metrics['total_itens'] == 2


def test_cliente_codigo_interno_regex(app_client):
    c = _novo_cliente(app_client,'Cliente Codigo','71111111000191')
    assert re.match(r'^C\d{5}$', c['codigo_interno'] or '')


def test_item_rev_capturada(app_client):
    c = _novo_cliente(app_client,'Cliente Rev','81111111000191')
    p = _novo_pedido(app_client, c['id'])
    _nova_emb(app_client,'EMB15', c['id'], rev='R01')
    resp_item = _add_item(app_client, p['id'],'EMB15', rev='R01')
    assert resp_item.status_code == 201
    it = resp_item.get_json()
    assert it['rev'] == 'R01'
