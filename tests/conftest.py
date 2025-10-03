import os
import tempfile
import pytest
from flask import session

"""Fixtures de teste.

Notas:
 - Usamos escopo de sessão para reaproveitar a mesma instância de app e um
   único banco temporário. Isso evita que o módulo app (que chama bootstrap_db
   no import) mantenha DB_PATH apontando para um diretório já removido entre
   testes (o que causava sqlite3.OperationalError: unable to open database file).
 - O isolamento total por teste poderia ser feito expondo uma factory create_app
   ou tornando DB_PATH dinâmico por conexão; para simplicidade optamos por
   reutilização. Os testes atuais não dependem de estado inicial vazio além de
   verificarem incrementos relativos (ex: numerador de pedidos) dentro do mesmo
   caso de teste.
"""

# Redirecionar path de banco antes de importar app (escopo sessão)
@pytest.fixture(scope="session")
def app_client():
  tmpdir = tempfile.TemporaryDirectory()
  db_path = os.path.join(tmpdir.name, 'test.db')
  os.environ['APP_DB_PATH'] = db_path
  # Importa app uma única vez; DB_PATH já aponta para o temp antes do import
  import app as app_module  # type: ignore
  app = app_module.app
  client = app.test_client()
  with client.session_transaction() as sess:
    sess['user_id'] = 1
    sess['user_email'] = 'tester@example.com'
    sess['user_papel'] = 'pcp'
  yield client
  tmpdir.cleanup()
