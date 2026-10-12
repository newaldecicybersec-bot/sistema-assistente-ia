import sqlite3, os, json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assistente.db')
LIMITES = {'basico': 500, 'profissional': 2000, 'empresarial': 5000}
VALORES = {'basico': 29, 'profissional': 59, 'empresarial': 149}

def get_db():
    db = sqlite3.connect(DB); db.row_factory = sqlite3.Row; return db

def init_db():
    db = get_db()
    db.executescript('''
    CREATE TABLE IF NOT EXISTS clientes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nome TEXT NOT NULL, email TEXT UNIQUE NOT NULL, senha TEXT NOT NULL,
      tipo TEXT, documento TEXT, telefone TEXT,
      plano TEXT DEFAULT 'basico',
      criado_em TEXT DEFAULT (datetime('now','localtime')));
    CREATE TABLE IF NOT EXISTS consumo (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      cliente_id INTEGER NOT NULL, mensagens INTEGER DEFAULT 0,
      registrado_em TEXT DEFAULT (datetime('now','localtime')));
    CREATE TABLE IF NOT EXISTS tokens (
      token TEXT PRIMARY KEY,
      cliente_id INTEGER NOT NULL,
      criado_em TEXT DEFAULT (datetime('now','localtime')));
    ''')
    db.commit(); db.close()

class API(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type')
        self.end_headers()

    def do_GET(self):
        db = get_db()
        if self.path == '/health':
            self._json({'status':'ok','servico':'Meu Assistente IA - Sistema'})
        elif self.path.startswith('/api/saldo/'):
            cid = int(self.path.rsplit('/',1)[1])
            auth = self.headers.get('Authorization','')
            tok = auth.replace('Bearer ','').strip()
            ok = db.execute('SELECT 1 FROM tokens WHERE token=? AND cliente_id=?',(tok,cid)).fetchone()
            if not ok: db.close(); return self._json({'erro':'nao autorizado'},401)
            c = db.execute('SELECT * FROM clientes WHERE id=?',(cid,)).fetchone()
            if not c: db.close(); return self._json({'erro':'nao encontrado'},404)
            usado = db.execute('SELECT COALESCE(SUM(mensagens),0) FROM consumo WHERE cliente_id=?',(cid,)).fetchone()[0]
            lim = LIMITES.get(c['plano'],500)
            self._json({'nome':c['nome'],'plano':c['plano'],'usado':usado,'limite':lim,'restante':max(0,lim-usado)})
        elif self.path.startswith('/api/admin/resumo'):
            admin_key = os.environ.get('ADMIN_KEY','meu-chave-admin-2026')
            given = self.headers.get('X-Admin-Key') or (self.path.split('key=')[1].split('&')[0] if 'key=' in self.path else '')
            if given != admin_key: db.close(); return self._json({'erro':'acesso negado'},403)
            total = db.execute('SELECT COUNT(*) FROM clientes').fetchone()[0]
            planos = db.execute('SELECT plano, COUNT(*) q FROM clientes GROUP BY plano').fetchall()
            receita = sum(VALORES.get(r['plano'],0)*r['q'] for r in planos)
            hoje = datetime.now().strftime('%Y-%m-%d')
            novos = db.execute("SELECT COUNT(*) FROM clientes WHERE date(criado_em)=?",(hoje,)).fetchone()[0]
            self._json({'total_clientes':total,'receita_mensal':receita,'novos_hoje':novos,
                        'planos':{r['plano']:r['q'] for r in planos}})
        else:
            self._json({'erro':'rota nao encontrada'},404)
        db.close()

    def do_POST(self):
        n = int(self.headers.get('Content-Length',0))
        d = json.loads(self.rfile.read(n) or b'{}')
        db = get_db()
        if self.path == '/api/registro':
            try:
                cur = db.execute('INSERT INTO clientes (nome,email,senha,tipo,documento,telefone,plano) VALUES (?,?,?,?,?,?,?)',
                    (d.get('nome'),d.get('email'),d.get('senha'),d.get('tipo'),d.get('documento'),d.get('telefone'),d.get('plano','basico')))
                db.commit(); self._json({'ok':True,'id':cur.lastrowid})
            except sqlite3.IntegrityError:
                self._json({'ok':False,'erro':'e-mail ja cadastrado'},409)
        elif self.path == '/api/login':
            c = db.execute('SELECT * FROM clientes WHERE email=? AND senha=?',(d.get('email'),d.get('senha'))).fetchone()
            if c:
                import secrets as _s
                tok = _s.token_urlsafe(24)
                db.execute('INSERT INTO tokens (token,cliente_id) VALUES (?,?)',(tok,c['id']))
                db.commit()
                self._json({'ok':True,'nome':c['nome'],'id':c['id'],'token':tok})
            else:
                self._json({'ok':False,'erro':'credenciais invalidas'},401)
        elif self.path == '/api/consumo':
            db.execute('INSERT INTO consumo (cliente_id,mensagens) VALUES (?,?)',(d['cliente_id'],d.get('mensagens',1)))
            db.commit(); self._json({'ok':True})
        else:
            self._json({'erro':'rota nao encontrada'},404)
        db.close()

    def log_message(self, *a): pass

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT',8000))
    print(f'Sistema Meu Assistente IA na porta {port}')
    HTTPServer(('0.0.0.0',port), API).serve_forever()
