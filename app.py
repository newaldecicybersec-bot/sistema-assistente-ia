import sqlite3, os
from datetime import datetime
from flask import Flask, request, jsonify, session, redirect, render_template_string, g

DB = os.path.join(os.path.dirname(__file__), 'assistente.db')
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'troque-esta-chave-em-producao')

# ---------------- Banco de dados ----------------
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db: db.close()

def init_db():
    db = sqlite3.connect(DB)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS clientes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nome TEXT NOT NULL,
      email TEXT UNIQUE NOT NULL,
      senha TEXT NOT NULL,
      tipo TEXT,
      documento TEXT,
      telefone TEXT,
      plano TEXT DEFAULT 'basico',
      criado_em TEXT DEFAULT (datetime('now','localtime'))
    );
    CREATE TABLE IF NOT EXISTS consumo (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      cliente_id INTEGER NOT NULL,
      mensagens INTEGER DEFAULT 0,
      registrado_em TEXT DEFAULT (datetime('now','localtime')),
      FOREIGN KEY(cliente_id) REFERENCES clientes(id)
    );
    ''')
    db.commit(); db.close()

LIMITES = {'basico': 500, 'profissional': 2000, 'empresarial': 5000}
VALORES = {'basico': 29, 'profissional': 59, 'empresarial': 149}

# ---------------- Roteamento ----------------
@app.route('/api/registro', methods=['POST'])
def registro():
    d = request.get_json(force=True)
    db = get_db()
    try:
        cur = db.execute(
            'INSERT INTO clientes (nome,email,senha,tipo,documento,telefone,plano) VALUES (?,?,?,?,?,?,?)',
            (d.get('nome'), d.get('email'), d.get('senha'), d.get('tipo'),
             d.get('documento'), d.get('telefone'), d.get('plano','basico')))
        db.commit()
        return jsonify(ok=True, id=cur.lastrowid)
    except sqlite3.IntegrityError:
        return jsonify(ok=False, erro='e-mail ja cadastrado'), 409

@app.route('/api/login', methods=['POST'])
def login():
    d = request.get_json(force=True)
    db = get_db()
    c = db.execute('SELECT * FROM clientes WHERE email=? AND senha=?',
                   (d.get('email'), d.get('senha'))).fetchone()
    if c:
        session['cliente'] = c['id']
        return jsonify(ok=True, nome=c['nome'])
    return jsonify(ok=False, erro='credenciais invalidas'), 401

@app.route('/api/consumo', methods=['POST'])
def consumo():
    d = request.get_json(force=True)
    db = get_db()
    db.execute('INSERT INTO consumo (cliente_id, mensagens) VALUES (?,?)',
               (d['cliente_id'], d.get('mensagens', 1)))
    db.commit()
    return jsonify(ok=True)

@app.route('/api/saldo/<int:cliente_id>')
def saldo(cliente_id):
    db = get_db()
    c = db.execute('SELECT * FROM clientes WHERE id=?', (cliente_id,)).fetchone()
    if not c: return jsonify(erro='nao encontrado'), 404
    usado = db.execute('SELECT COALESCE(SUM(mensagens),0) FROM consumo WHERE cliente_id=?',
                       (cliente_id,)).fetchone()[0]
    limite = LIMITES.get(c['plano'], 500)
    return jsonify(nome=c['nome'], plano=c['plano'], usado=usado, limite=limite,
                   restante=max(0, limite-usado))

@app.route('/api/admin/resumo')
def resumo():
    db = get_db()
    total = db.execute('SELECT COUNT(*) FROM clientes').fetchone()[0]
    por_plano = db.execute('SELECT plano, COUNT(*) q FROM clientes GROUP BY plano').fetchall()
    receita = sum(VALORES.get(r['plano'],0)*r['q'] for r in por_plano)
    hoje = datetime.now().strftime('%Y-%m-%d')
    novos_hoje = db.execute("SELECT COUNT(*) FROM clientes WHERE date(criado_em)=?", (hoje,)).fetchone()[0]
    return jsonify(total_clientes=total, receita_mensal=receita, novos_hoje=novos_hoje,
                   planos={r['plano']: r['q'] for r in por_plano})

@app.route('/health')
def health():
    return jsonify(status='ok', servico='Meu Assistente IA - Sistema')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8000)), debug=False)
