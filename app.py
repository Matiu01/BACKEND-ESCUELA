from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import sqlite3
import os
from werkzeug.utils import secure_filename
import json

app = Flask(__name__)
CORS(app)

# === RUTAS ABSOLUTAS PARA RENDER / SERVIDOR ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "colegios.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # colegios
    c.execute("""
    CREATE TABLE IF NOT EXISTS colegios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE
    )
    """)

    # =============== ASISTENCIA BIOMÉTRICA (ENTRADA / SALIDA) ===============
    c.execute("""
    CREATE TABLE IF NOT EXISTS asistencia_marcaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colegio TEXT,
        usuario_id INTEGER,
        usuario_nombre TEXT,
        email TEXT,
        tipo TEXT,             -- 'entrada' o 'salida'
        timestamp TEXT DEFAULT (datetime('now','localtime'))
    )
    """)

    # ===== usuarios con UNIQUE(email, colegio) =====
    c.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        email TEXT,
        password TEXT,
        rol TEXT,
        colegio TEXT,
        UNIQUE (email, colegio)
    )
    """)

    # --- Migración si la tabla vieja tenía email UNIQUE (global) ---
    try:
        row = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='usuarios'").fetchone()
        create_sql = (row["sql"] if row else "") or ""
        if "email TEXT UNIQUE" in create_sql or ("UNIQUE" in create_sql and "(email)" in create_sql and "colegio" not in create_sql):
            conn.executescript("""
            PRAGMA foreign_keys=OFF;
            BEGIN TRANSACTION;
            CREATE TABLE IF NOT EXISTS usuarios_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                email TEXT,
                password TEXT,
                rol TEXT,
                colegio TEXT,
                UNIQUE (email, colegio)
            );
            INSERT OR IGNORE INTO usuarios_new (id, nombre, email, password, rol, colegio)
            SELECT id, nombre, email, password, rol, colegio FROM usuarios;
            DROP TABLE usuarios;
            ALTER TABLE usuarios_new RENAME TO usuarios;
            COMMIT;
            PRAGMA foreign_keys=ON;
            """)
    except Exception as e:
        print("Aviso migración usuarios:", e)

    # documentos
    c.execute("""
    CREATE TABLE IF NOT EXISTS documentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre_original TEXT,
        nombre_fisico TEXT,
        colegio TEXT,
        categoria TEXT,
        subido_por TEXT,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # categorias de doc
    c.execute("""
    CREATE TABLE IF NOT EXISTS documento_categorias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colegio TEXT,
        nombre TEXT,
        UNIQUE (colegio, nombre)
    )
    """)

    # horarios
    c.execute("""
    CREATE TABLE IF NOT EXISTS horarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colegio TEXT,
        docente TEXT,
        data TEXT,
        UNIQUE (colegio, docente)
    )
    """)

    # eventos
    c.execute("""
    CREATE TABLE IF NOT EXISTS eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colegio TEXT,
        titulo TEXT,
        descripcion TEXT,
        fecha_inicio TEXT,
        fecha_fin TEXT
    )
    """)

    # asistencia QR (cabecera)
    c.execute("""
    CREATE TABLE IF NOT EXISTS asistencia_qr (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colegio TEXT,
        titulo TEXT,
        campos TEXT,
        fecha_inicio TEXT,
        fecha_fin TEXT,
        qr_string TEXT
    )
    """)

    # registros de asistencia (formularios QR)
    c.execute("""
    CREATE TABLE IF NOT EXISTS asistencia_registros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        qr_id INTEGER,
        datos TEXT,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # cursos
    c.execute("""
    CREATE TABLE IF NOT EXISTS cursos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colegio TEXT,
        nombre TEXT,
        nivel TEXT,
        turno TEXT,
        UNIQUE (colegio, nombre, turno)
    )
    """)

    # estudiantes
    c.execute("""
    CREATE TABLE IF NOT EXISTS estudiantes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colegio TEXT,
        curso_id INTEGER,
        nombre TEXT,
        rude TEXT,
        ci TEXT,
        fecha_nac TEXT,
        estado TEXT,
        padre_nombre TEXT,
        padre_ci TEXT,
        padre_fecha_nac TEXT,
        padre_cel TEXT,
        madre_nombre TEXT,
        madre_ci TEXT,
        madre_fecha_nac TEXT,
        madre_cel TEXT,
        tutor_nombre TEXT,
        tutor_cel TEXT,
        FOREIGN KEY(curso_id) REFERENCES cursos(id)
    )
    """)

    # comisiones y profesores
    c.execute("""
    CREATE TABLE IF NOT EXISTS comisiones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colegio TEXT,
        nombre TEXT,
        UNIQUE (colegio, nombre)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS profesores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        colegio TEXT,
        nombre TEXT,
        carnet TEXT,
        cargo TEXT,
        fecha_nac TEXT,
        cel1 TEXT,
        cel2 TEXT,
        cel_extra TEXT,
        asesor_curso TEXT,
        comision TEXT,
        clases TEXT,
        extra_campos TEXT
    )
    """)

    conn.commit()
    conn.close()


@app.route("/")
def home():
    return "API Sistema Escolar funcionando ✅"


# =============== COLEGIOS / LOGIN / USUARIOS =================
@app.route("/colegios", methods=["GET"])
def get_colegios():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT nombre FROM colegios")
    data = [row["nombre"] for row in c.fetchall()]
    conn.close()
    return jsonify({"colegios": data})


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    colegio = data.get("colegio")

    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, nombre, email, rol, colegio
        FROM usuarios
        WHERE email=? AND password=? AND colegio=?
    """, (email, password, colegio))
    row = c.fetchone()
    conn.close()

    if row:
        return jsonify({
            "id": row["id"],
            "nombre": row["nombre"],
            "email": row["email"],
            "rol": row["rol"],
            "colegio": row["colegio"],
        })
    else:
        return jsonify({"error": "Credenciales incorrectas"}), 401


@app.route("/registrar_usuario", methods=["POST"])
def registrar_usuario():
    data = request.get_json()
    nombre = data.get("nombre")
    email = data.get("email")
    password = data.get("password")
    rol = data.get("rol", "docente")

    nuevo_colegio = data.get("nuevo_colegio")
    colegio = data.get("colegio")

    if not all([nombre, email, password, rol]):
        return jsonify({"error": "faltan datos"}), 400

    conn = get_conn()
    c = conn.cursor()

    # crear colegio si vino
    if nuevo_colegio:
        c.execute("SELECT id FROM colegios WHERE nombre=?", (nuevo_colegio,))
        row = c.fetchone()
        if not row:
            c.execute("INSERT INTO colegios (nombre) VALUES (?)", (nuevo_colegio,))
        colegio = nuevo_colegio

    if not colegio:
        conn.close()
        return jsonify({"error": "no hay colegio especificado"}), 400

    # duplicado solo dentro del MISMO colegio
    c.execute("SELECT id FROM usuarios WHERE email=? AND colegio=?", (email, colegio))
    if c.fetchone():
        conn.close()
        return jsonify({"error": "correo ya registrado en este colegio"}), 400

    c.execute("""
        INSERT INTO usuarios (nombre, email, password, rol, colegio)
        VALUES (?, ?, ?, ?, ?)
    """, (nombre, email, password, rol, colegio))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "usuario creado"}), 200


@app.route("/usuarios/<colegio>", methods=["GET"])
def usuarios_por_colegio(colegio):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, nombre, email, rol, colegio
        FROM usuarios
        WHERE colegio = ?
        ORDER BY id DESC
    """, (colegio,))
    usuarios = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({"usuarios": usuarios})


# =============== DOCUMENTOS / HORARIOS / EVENTOS ===============
@app.route("/documentos/categorias/<colegio>", methods=["GET"])
def listar_categorias(colegio):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT nombre FROM documento_categorias
        WHERE colegio = ?
        ORDER BY nombre
    """, (colegio,))
    cats = [row["nombre"] for row in c.fetchall()]
    conn.close()
    if not cats:
        cats = ["General", "Reportes", "Constancias"]
    return jsonify({"categorias": cats})


@app.route("/documentos/categorias", methods=["POST"])
def crear_categoria():
    data = request.get_json()
    colegio = data.get("colegio")
    nombre = data.get("nombre")
    if not colegio or not nombre:
        return jsonify({"error": "faltan datos"}), 400
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO documento_categorias (colegio, nombre)
        VALUES (?, ?)
    """, (colegio, nombre))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "categoria creada"}), 200


@app.route("/documentos/categorias", methods=["DELETE"])
def borrar_categoria_documentos():
    data = request.get_json(silent=True) or {}
    colegio = data.get("colegio")
    nombre = data.get("nombre")
    if not colegio or not nombre:
        return jsonify({"error": "faltan datos"}), 400
    if nombre == "General":
        return jsonify({"error": "no se puede eliminar 'General'"}), 400

    conn = get_conn()
    c = conn.cursor()
    # Asegurar que exista "General"
    c.execute("""
        INSERT OR IGNORE INTO documento_categorias (colegio, nombre)
        VALUES (?, 'General')
    """, (colegio,))
    # Mover documentos a "General"
    c.execute("""
        UPDATE documentos
        SET categoria = 'General'
        WHERE colegio = ? AND categoria = ?
    """, (colegio, nombre))
    # Borrar la categoría
    c.execute("""
        DELETE FROM documento_categorias
        WHERE colegio = ? AND nombre = ?
    """, (colegio, nombre))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "categoria eliminada; documentos movidos a 'General'"}), 200


@app.route("/documentos/<colegio>", methods=["GET"])
def listar_documentos(colegio):
    categoria = request.args.get("categoria", "General")
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, nombre_original, colegio, categoria, subido_por, creado_en
        FROM documentos
        WHERE colegio = ? AND categoria = ?
        ORDER BY creado_en DESC
    """, (colegio, categoria))
    docs = []
    for row in c.fetchall():
        docs.append({
            "id": row["id"],
            "nombre": row["nombre_original"],
            "colegio": row["colegio"],
            "categoria": row["categoria"],
            "subido_por": row["subido_por"],
            "creado_en": row["creado_en"],
        })
    conn.close()
    return jsonify({"archivos": docs})


@app.route("/documentos/upload", methods=["POST"])
def subir_documento():
    if "archivo" not in request.files:
        return jsonify({"error": "no se envió archivo"}), 400
    archivo = request.files["archivo"]
    colegio = request.form.get("colegio")
    categoria = request.form.get("categoria", "General")
    subido_por = request.form.get("subido_por", "app")
    if not colegio:
        return jsonify({"error": "falta colegio"}), 400
    if archivo.filename == "":
        return jsonify({"error": "archivo sin nombre"}), 400

    filename_seguro = secure_filename(archivo.filename)
    ruta_guardar = os.path.join(UPLOAD_FOLDER, filename_seguro)
    base_name = filename_seguro
    contador = 1
    while os.path.exists(ruta_guardar):
        name, ext = os.path.splitext(base_name)
        filename_seguro = f"{name}_{contador}{ext}"
        ruta_guardar = os.path.join(UPLOAD_FOLDER, filename_seguro)
        contador += 1
    archivo.save(ruta_guardar)

    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO documento_categorias (colegio, nombre)
        VALUES (?, ?)
    """, (colegio, categoria))
    c.execute("""
        INSERT INTO documentos (nombre_original, nombre_fisico, colegio, categoria, subido_por)
        VALUES (?, ?, ?, ?, ?)
    """, (archivo.filename, filename_seguro, colegio, categoria, subido_por))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "archivo subido"}), 200


@app.route("/documentos/download/<int:doc_id>", methods=["GET"])
def descargar_documento(doc_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT nombre_original, nombre_fisico
        FROM documentos
        WHERE id = ?
    """, (doc_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "no existe documento"}), 404
    return send_from_directory(
        UPLOAD_FOLDER,
        row["nombre_fisico"],
        as_attachment=True,
        download_name=row["nombre_original"],
    )


@app.route("/docentes/<colegio>", methods=["GET"])
def listar_docentes(colegio):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT nombre, email FROM usuarios
        WHERE colegio = ? AND rol = 'docente'
        ORDER BY nombre
    """, (colegio,))
    docentes = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({"docentes": docentes})


@app.route("/horarios/<colegio>", methods=["GET"])
def listar_horarios_colegio(colegio):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT docente, data FROM horarios WHERE colegio = ?", (colegio,))
    items = []
    for row in c.fetchall():
        items.append({"docente": row["docente"], "horario": json.loads(row["data"])})
    conn.close()
    return jsonify({"horarios": items})


@app.route("/horarios/<colegio>/<docente_email>", methods=["GET"])
def get_horario(colegio, docente_email):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, data FROM horarios
        WHERE colegio = ? AND docente = ?
    """, (colegio, docente_email))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({"horario": {}, "id": None})
    return jsonify({"horario": json.loads(row["data"]), "id": row["id"]})


@app.route("/horarios", methods=["POST"])
def guardar_horario():
    data = request.get_json()
    colegio = data.get("colegio")
    docente = data.get("docente")
    horario_data = data.get("horario")
    if not colegio or not docente or horario_data is None:
        return jsonify({"error": "faltan datos"}), 400
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM horarios WHERE colegio=? AND docente=?", (colegio, docente))
    row = c.fetchone()
    if row:
        c.execute("UPDATE horarios SET data=? WHERE id=?", (json.dumps(horario_data), row["id"]))
    else:
        c.execute("INSERT INTO horarios (colegio, docente, data) VALUES (?, ?, ?)",
                  (colegio, docente, json.dumps(horario_data)))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "horario guardado"}), 200


@app.route("/horarios/<colegio>/<docente_email>", methods=["DELETE"])
def eliminar_horario(colegio, docente_email):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM horarios WHERE colegio=? AND docente=?", (colegio, docente_email))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "horario eliminado"}), 200


@app.route("/eventos/<colegio>", methods=["GET"])
@app.route("/eventos/<colegio>/", methods=["GET"])
def listar_eventos(colegio):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, colegio, titulo, descripcion, fecha_inicio, fecha_fin
        FROM eventos
        WHERE colegio = ?
        ORDER BY fecha_inicio
    """, (colegio,))
    rows = c.fetchall()
    conn.close()
    eventos = []
    for r in rows:
        eventos.append({
            "id": r["id"],
            "colegio": r["colegio"],
            "titulo": r["titulo"],
            "descripcion": r["descripcion"],
            "fecha_inicio": r["fecha_inicio"],
            "fecha_fin": r["fecha_fin"],
        })
    return jsonify({"eventos": eventos})


@app.route("/eventos", methods=["POST"])
@app.route("/eventos/", methods=["POST"])
def crear_evento():
    data = request.get_json()
    colegio = data.get("colegio")
    titulo = data.get("titulo")
    descripcion = data.get("descripcion", "")
    fecha_inicio = data.get("fecha_inicio")
    fecha_fin = data.get("fecha_fin") or fecha_inicio
    if not colegio or not titulo or not fecha_inicio:
        return jsonify({"error": "faltan datos"}), 400
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO eventos (colegio, titulo, descripcion, fecha_inicio, fecha_fin)
        VALUES (?, ?, ?, ?, ?)
    """, (colegio, titulo, descripcion, fecha_inicio, fecha_fin))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "evento creado"}), 200


@app.route("/eventos/<int:evento_id>", methods=["PUT"])
@app.route("/eventos/<int:evento_id>/", methods=["PUT"])
def actualizar_evento(evento_id):
    data = request.get_json()
    colegio = data.get("colegio")
    titulo = data.get("titulo")
    descripcion = data.get("descripcion", "")
    fecha_inicio = data.get("fecha_inicio")
    fecha_fin = data.get("fecha_fin") or fecha_inicio
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM eventos WHERE id=?", (evento_id,))
    if not c.fetchone():
        conn.close()
        return jsonify({"error": "evento no encontrado"}), 404
    c.execute("""
        UPDATE eventos
        SET colegio=?, titulo=?, descripcion=?, fecha_inicio=?, fecha_fin=?
        WHERE id=?
    """, (colegio, titulo, descripcion, fecha_inicio, fecha_fin, evento_id))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "evento actualizado"}), 200


@app.route("/eventos/<int:evento_id>", methods=["DELETE"])
@app.route("/eventos/<int:evento_id>/", methods=["DELETE"])
def eliminar_evento(evento_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM eventos WHERE id=?", (evento_id,))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "evento eliminado"}), 200


# =============== ASISTENCIA QR (FORMULARIOS) ===============
@app.route("/asistencia_qr/<colegio>", methods=["GET"])
@app.route("/asistencia_qr/<colegio>/", methods=["GET"])
def listar_asistencia_qr(colegio):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, colegio, titulo, campos, fecha_inicio, fecha_fin, qr_string
        FROM asistencia_qr
        WHERE colegio=?
        ORDER BY fecha_inicio DESC, id DESC
    """, (colegio,))
    items = []
    for row in c.fetchall():
        try:
            campos = json.loads(row["campos"] or "[]")
        except Exception:
            campos = []
        items.append({
            "id": row["id"],
            "colegio": row["colegio"],
            "titulo": row["titulo"],
            "campos": campos,
            "fecha_inicio": row["fecha_inicio"],
            "fecha_fin": row["fecha_fin"],
            "qr_string": row["qr_string"],
        })
    conn.close()
    return jsonify({"items": items})


@app.route("/asistencia_qr", methods=["POST"])
@app.route("/asistencia_qr/", methods=["POST"])
def crear_asistencia_qr():
    data = request.get_json()
    colegio = data.get("colegio")
    titulo = data.get("titulo")
    campos = data.get("campos", [])
    fecha_inicio = data.get("fecha_inicio")
    fecha_fin = data.get("fecha_fin")

    if not colegio or not titulo or not fecha_inicio:
        return jsonify({"error": "faltan datos"}), 400

    campos_limpios = [str(x).strip() for x in campos if str(x).strip()]

    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        INSERT INTO asistencia_qr (colegio, titulo, campos, fecha_inicio, fecha_fin, qr_string)
        VALUES (?, ?, ?, ?, ?, '')
    """, (colegio, titulo, json.dumps(campos_limpios), fecha_inicio, fecha_fin))
    qr_id = c.lastrowid

    qr_payload = json.dumps({"qr_id": qr_id, "colegio": colegio})
    c.execute("UPDATE asistencia_qr SET qr_string=? WHERE id=?", (qr_payload, qr_id))

    conn.commit()

    c.execute("""
        SELECT id, colegio, titulo, campos, fecha_inicio, fecha_fin, qr_string
        FROM asistencia_qr
        WHERE id=?
    """, (qr_id,))
    row = c.fetchone()
    conn.close()

    item = {
        "id": row["id"],
        "colegio": row["colegio"],
        "titulo": row["titulo"],
        "campos": json.loads(row["campos"] or "[]"),
        "fecha_inicio": row["fecha_inicio"],
        "fecha_fin": row["fecha_fin"],
        "qr_string": row["qr_string"],
    }

    return jsonify({"mensaje": "qr creado", "item": item}), 200


@app.route("/asistencia_qr/<int:qr_id>", methods=["DELETE"])
@app.route("/asistencia_qr/<int:qr_id>/", methods=["DELETE"])
def borrar_asistencia_qr(qr_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM asistencia_registros WHERE qr_id=?", (qr_id,))
    c.execute("DELETE FROM asistencia_qr WHERE id=?", (qr_id,))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "qr eliminado"}), 200


@app.route("/asistencia_qr/registrar", methods=["POST"])
def registrar_asistencia():
    data = request.get_json()
    qr_id = data.get("qr_id")
    datos = data.get("datos", {})

    if not qr_id:
        return jsonify({"error": "falta qr_id"}), 400

    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO asistencia_registros (qr_id, datos)
        VALUES (?, ?)
    """, (qr_id, json.dumps(datos)))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "asistencia registrada"}), 200


@app.route("/asistencia_qr/registros/<int:qr_id>", methods=["GET"])
def listar_registros_qr(qr_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, qr_id, datos, creado_en
        FROM asistencia_registros
        WHERE qr_id=?
        ORDER BY creado_en DESC
    """, (qr_id,))
    registros = []
    for row in c.fetchall():
        try:
            datos = json.loads(row["datos"] or "{}")
        except Exception:
            datos = {}
        registros.append({
            "id": row["id"],
            "qr_id": row["qr_id"],
            "datos": datos,
            "creado_en": row["creado_en"],
        })
    conn.close()
    return jsonify({"registros": registros})


@app.route("/asistencia_qr/estadisticas/<colegio>", methods=["GET"])
@app.route("/asistencia_qr/estadisticas/<colegio>/", methods=["GET"])
def estadisticas_asistencia(colegio):
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")

    conn = get_conn()
    c = conn.cursor()

    params = [colegio]
    filtro = ""
    if desde:
        filtro += " AND datetime(aq.fecha_inicio) >= datetime(?)"
        params.append(desde)
    if hasta:
        filtro += " AND datetime(aq.fecha_inicio) <= datetime(?)"
        params.append(hasta)

    c.execute(f"""
        SELECT aq.id AS qr_id,
               aq.titulo,
               aq.fecha_inicio,
               aq.fecha_fin,
               COUNT(ar.id) AS total_respuestas
        FROM asistencia_qr aq
        LEFT JOIN asistencia_registros ar ON ar.qr_id = aq.id
        WHERE aq.colegio = ? {filtro}
        GROUP BY aq.id, aq.titulo, aq.fecha_inicio, aq.fecha_fin
        ORDER BY aq.fecha_inicio DESC, qr_id DESC
    """, params)

    items = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({"items": items})


# =============== ASISTENCIA BIOMÉTRICA: ENDPOINTS GENERALES ===============
@app.route("/asistencia_marcacion", methods=["POST"])
def registrar_marcacion():
    """
    Body esperado (todo opcional excepto colegio y tipo):
    {
      "colegio": "LAS ROSAS",
      "usuario_id": 1,
      "usuario_nombre": "Mateo",
      "email": "mate@gmail.com",
      "tipo": "entrada" | "salida"
    }
    """
    data = request.get_json() or {}
    colegio = data.get("colegio")
    tipo = (data.get("tipo") or "").lower()
    usuario_id = data.get("usuario_id")
    usuario_nombre = data.get("usuario_nombre")
    email = data.get("email")

    if not colegio or tipo not in ("entrada", "salida"):
        return jsonify({"error": "faltan datos o tipo inválido"}), 400

    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO asistencia_marcaciones (colegio, usuario_id, usuario_nombre, email, tipo)
        VALUES (?, ?, ?, ?, ?)
    """, (colegio, usuario_id, usuario_nombre, email, tipo))
    conn.commit()

    marc_id = c.lastrowid
    c.execute("""
        SELECT id, colegio, usuario_id, usuario_nombre, email, tipo, timestamp
        FROM asistencia_marcaciones
        WHERE id=?
    """, (marc_id,))
    row = c.fetchone()
    conn.close()

    item = dict(row)
    return jsonify({"mensaje": "marcacion registrada", "item": item}), 200


@app.route("/asistencia_marcaciones_resumen/<colegio>", methods=["GET"])
def resumen_marcaciones(colegio):
    """
    Resumen simple por día y usuario.
    Opcional: ?desde=YYYY-MM-DD&hasta=YYYY-MM-DD
    """
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")

    conn = get_conn()
    c = conn.cursor()

    params = [colegio]
    filtro = ""
    if desde:
        filtro += " AND date(timestamp) >= date(?)"
        params.append(desde)
    if hasta:
        filtro += " AND date(timestamp) <= date(?)"
        params.append(hasta)

    c.execute(f"""
        SELECT
          date(timestamp) AS fecha,
          usuario_nombre,
          email,
          SUM(CASE WHEN tipo='entrada' THEN 1 ELSE 0 END) AS entradas,
          SUM(CASE WHEN tipo='salida' THEN 1 ELSE 0 END) AS salidas,
          COUNT(*) AS total
        FROM asistencia_marcaciones
        WHERE colegio=? {filtro}
        GROUP BY fecha, usuario_nombre, email
        ORDER BY fecha DESC, usuario_nombre
    """, params)

    items = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({"items": items})


# =============== ASISTENCIA BIOMÉTRICA: BÚSQUEDA INDIVIDUAL ===============
@app.route("/asistencia_marcaciones/buscar_usuarios/<colegio>", methods=["GET"])
def biometrico_buscar_usuarios(colegio):
    """
    Buscar personas que tengan marcaciones en un colegio.
    GET /asistencia_marcaciones/buscar_usuarios/LAS%20ROSAS?q=pedro
    Devuelve: { items: [ {usuario_nombre, email, total} ] }
    """
    q = (request.args.get("q") or "").strip().lower()

    conn = get_conn()
    c = conn.cursor()

    params = [colegio]
    filtro = "WHERE colegio = ?"
    if q:
        filtro += " AND (LOWER(usuario_nombre) LIKE ? OR LOWER(email) LIKE ?)"
        like_pat = f"%{q}%"
        params.extend([like_pat, like_pat])

    c.execute(f"""
        SELECT usuario_nombre,
               email,
               COUNT(*) AS total
        FROM asistencia_marcaciones
        {filtro}
        GROUP BY usuario_nombre, email
        ORDER BY usuario_nombre
        LIMIT 100
    """, params)

    items = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({"items": items})


@app.route("/asistencia_marcaciones/detalle_usuario/<colegio>", methods=["GET"])
def biometrico_detalle_usuario(colegio):
    """
    Detalle de marcaciones de una persona en un rango de fechas.
    GET /asistencia_marcaciones/detalle_usuario/LAS%20ROSAS?nombre=...&email=...&desde=YYYY-MM-DD&hasta=YYYY-MM-DD
    """
    nombre = request.args.get("nombre") or ""
    email = request.args.get("email") or ""
    desde = request.args.get("desde")  # YYYY-MM-DD
    hasta = request.args.get("hasta")  # YYYY-MM-DD

    conn = get_conn()
    c = conn.cursor()

    where = ["m.colegio = ?"]
    params = [colegio]

    if nombre:
        where.append("m.usuario_nombre = ?")
        params.append(nombre)
    if email:
        where.append("m.email = ?")
        params.append(email)
    if desde:
        where.append("date(m.timestamp) >= date(?)")
        params.append(desde)
    if hasta:
        where.append("date(m.timestamp) <= date(?)")
        params.append(hasta)

    where_sql = " AND ".join(where)

    c.execute(f"""
        SELECT
          m.id,
          m.usuario_nombre,
          m.email,
          m.tipo,
          m.timestamp
        FROM asistencia_marcaciones m
        WHERE {where_sql}
        ORDER BY m.timestamp
    """, params)

    items = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({"items": items})


# =============== ASISTENCIA BIOMÉTRICA: ENDPOINTS PARA LA APP (QR PUERTA) ===============
@app.route("/asistencia_biometrico/marcar", methods=["POST"])
def marcar_biometrico():
    """
    Endpoint que usa la app AsistenciaBiometricoScreen.
    Body:
    {
      "colegio": "...",
      "usuario_nombre": "...",
      "email": "...",
      "tipo": "entrada" | "salida"
    }
    """
    data = request.get_json() or {}
    colegio = data.get("colegio")
    usuario_nombre = data.get("usuario_nombre")
    email = data.get("email", "")
    tipo = (data.get("tipo") or "").lower()

    if not colegio or not usuario_nombre or tipo not in ("entrada", "salida"):
        return jsonify({"error": "datos inválidos"}), 400

    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO asistencia_marcaciones (colegio, usuario_id, usuario_nombre, email, tipo)
        VALUES (?, NULL, ?, ?, ?)
    """, (colegio, usuario_nombre, email, tipo))
    marc_id = c.lastrowid
    conn.commit()

    c.execute("""
        SELECT id, colegio, usuario_id, usuario_nombre, email, tipo, timestamp
        FROM asistencia_marcaciones
        WHERE id=?
    """, (marc_id,))
    row = c.fetchone()
    conn.close()

    return jsonify({
        "mensaje": "marcacion registrada",
        "item": dict(row)
    }), 200


@app.route("/asistencia_biometrico/registros/<colegio>", methods=["GET"])
def listar_marcaciones(colegio):
    """
    Devuelve el 'libro' de marcaciones del biométrico para un colegio.
    /asistencia_biometrico/registros/LAS%20ROSAS?desde=2025-01-01&hasta=2025-12-31
    """
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")

    conn = get_conn()
    c = conn.cursor()

    params = [colegio]
    filtro = ""
    if desde:
        filtro += " AND datetime(timestamp) >= datetime(?)"
        params.append(desde)
    if hasta:
        filtro += " AND datetime(timestamp) <= datetime(?)"
        params.append(hasta)

    c.execute(f"""
        SELECT id, colegio, usuario_id, usuario_nombre, email, tipo, timestamp
        FROM asistencia_marcaciones
        WHERE colegio=? {filtro}
        ORDER BY timestamp DESC, id DESC
    """, params)

    items = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({"items": items}), 200


# =============== ASISTENCIA BIOMÉTRICA: RESUMEN FECHA A FECHA ===============
@app.route("/asistencia_biometrico/fecha_a_fecha/<colegio>", methods=["GET"])
def biometrico_fecha_a_fecha(colegio):
    """
    Informe tipo 'Entradas/Salidas vs Fecha a Fecha'.
    """
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")

    conn = get_conn()
    c = conn.cursor()

    params = [colegio]
    filtro = ""
    if desde:
        filtro += " AND date(timestamp) >= date(?)"
        params.append(desde)
    if hasta:
        filtro += " AND date(timestamp) <= date(?)"
        params.append(hasta)

    # Agrupamos por usuario y fecha
    c.execute(f"""
        SELECT
          usuario_nombre,
          IFNULL(email, '') AS email,
          date(timestamp) AS fecha,
          SUM(CASE WHEN tipo='entrada' THEN 1 ELSE 0 END) AS entradas,
          SUM(CASE WHEN tipo='salida' THEN 1 ELSE 0 END) AS salidas
        FROM asistencia_marcaciones
        WHERE colegio=? {filtro}
        GROUP BY usuario_nombre, email, date(timestamp)
        ORDER BY usuario_nombre, fecha
    """, params)

    rows = c.fetchall()
    conn.close()

    # Reorganizamos: un registro por usuario, con lista de fechas
    usuarios = {}
    for r in rows:
        key = (r["usuario_nombre"], r["email"])
        if key not in usuarios:
            usuarios[key] = {
                "usuario_nombre": r["usuario_nombre"],
                "email": r["email"],
                "total_entradas": 0,
                "total_salidas": 0,
                "fechas": []
            }
        usuarios[key]["total_entradas"] += r["entradas"]
        usuarios[key]["total_salidas"] += r["salidas"]
        usuarios[key]["fechas"].append({
            "fecha": r["fecha"],
            "entradas": r["entradas"],
            "salidas": r["salidas"],
        })

    items = list(usuarios.values())
    return jsonify({"items": items}), 200


# =============== CURSOS / ESTUDIANTES / PROFESORES ===============
@app.route("/cursos/<colegio>", methods=["GET"])
def listar_cursos(colegio):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, nombre, nivel, turno
        FROM cursos
        WHERE colegio=?
        ORDER BY nombre
    """, (colegio,))
    cursos = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({"cursos": cursos})


@app.route("/cursos", methods=["POST"])
def crear_curso():
    data = request.get_json()
    colegio = data.get("colegio")
    nombre = data.get("nombre")
    nivel = data.get("nivel", "")
    turno = data.get("turno", "")
    if not colegio or not nombre:
        return jsonify({"error": "faltan datos"}), 400
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO cursos (colegio, nombre, nivel, turno)
        VALUES (?, ?, ?, ?)
    """, (colegio, nombre, nivel, turno))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "curso creado"}), 200


@app.route("/cursos/<int:curso_id>", methods=["DELETE"])
def eliminar_curso(curso_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM estudiantes WHERE curso_id=?", (curso_id,))
    c.execute("DELETE FROM cursos WHERE id=?", (curso_id,))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "curso eliminado"}), 200


@app.route("/estudiantes/<colegio>", methods=["GET"])
def listar_estudiantes(colegio):
    curso_id = request.args.get("curso_id")
    conn = get_conn()
    c = conn.cursor()
    if curso_id:
        c.execute("""
            SELECT * FROM estudiantes
            WHERE colegio=? AND curso_id=?
            ORDER BY nombre
        """, (colegio, curso_id))
    else:
        c.execute("""
            SELECT * FROM estudiantes
            WHERE colegio=?
            ORDER BY nombre
        """, (colegio,))
    ests = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({"estudiantes": ests})


@app.route("/estudiantes", methods=["POST"])
def crear_estudiante():
    data = request.get_json()
    colegio = data.get("colegio")
    curso_id = data.get("curso_id")
    nombre = data.get("nombre", "")
    rude = data.get("rude", "")
    ci = data.get("ci", "")
    fecha_nac = data.get("fecha_nac", "")
    estado = data.get("estado", "")
    padre_nombre = data.get("padre_nombre", "")
    padre_ci = data.get("padre_ci", "")
    padre_fecha_nac = data.get("padre_fecha_nac", "")
    padre_cel = data.get("padre_cel", "")
    madre_nombre = data.get("madre_nombre", "")
    madre_ci = data.get("madre_ci", "")
    madre_fecha_nac = data.get("madre_fecha_nac", "")
    madre_cel = data.get("madre_cel", "")
    tutor_nombre = data.get("tutor_nombre", "")
    tutor_cel = data.get("tutor_cel", "")

    if not colegio or not curso_id or not nombre:
        return jsonify({"error": "faltan datos"}), 400

    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO estudiantes (
            colegio, curso_id, nombre, rude, ci, fecha_nac, estado,
            padre_nombre, padre_ci, padre_fecha_nac, padre_cel,
            madre_nombre, madre_ci, madre_fecha_nac, madre_cel,
            tutor_nombre, tutor_cel
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        colegio, curso_id, nombre, rude, ci, fecha_nac, estado,
        padre_nombre, padre_ci, padre_fecha_nac, padre_cel,
        madre_nombre, madre_ci, madre_fecha_nac, madre_cel,
        tutor_nombre, tutor_cel
    ))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "estudiante creado"}), 200


@app.route("/estudiantes/<int:est_id>", methods=["PUT"])
def actualizar_estudiante(est_id):
    data = request.get_json()
    campos = [
        "nombre", "rude", "ci", "fecha_nac", "estado",
        "padre_nombre", "padre_ci", "padre_fecha_nac", "padre_cel",
        "madre_nombre", "madre_ci", "madre_fecha_nac", "madre_cel",
        "tutor_nombre", "tutor_cel"
    ]
    sets = []
    valores = []
    for cpo in campos:
        if cpo in data:
            sets.append(f"{cpo}=?")
            valores.append(data[cpo])
    if not sets:
        return jsonify({"error": "nada que actualizar"}), 400
    valores.append(est_id)
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"UPDATE estudiantes SET {', '.join(sets)} WHERE id=?", valores)
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "estudiante actualizado"}), 200


@app.route("/estudiantes/<int:est_id>", methods=["DELETE"])
def eliminar_estudiante(est_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM estudiantes WHERE id=?", (est_id,))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "estudiante eliminado"}), 200


@app.route("/comisiones/<colegio>", methods=["GET"])
def listar_comisiones(colegio):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, nombre FROM comisiones
        WHERE colegio=? ORDER BY nombre
    """, (colegio,))
    arr = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({"comisiones": arr})


@app.route("/comisiones", methods=["POST"])
def crear_comision():
    data = request.get_json()
    colegio = data.get("colegio")
    nombre = data.get("nombre")
    if not colegio or not nombre:
        return jsonify({"error": "faltan datos"}), 400
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO comisiones (colegio, nombre)
        VALUES (?, ?)
    """, (colegio, nombre))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "comision creada"}), 200


@app.route("/comisiones/<int:com_id>", methods=["DELETE"])
def eliminar_comision(com_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT colegio, nombre FROM comisiones WHERE id=?", (com_id,))
    row = c.fetchone()
    if row:
        colegio, nombre = row["colegio"], row["nombre"]
        c.execute("UPDATE profesores SET comision='' WHERE colegio=? AND comision=?", (colegio, nombre))
        c.execute("DELETE FROM comisiones WHERE id=?", (com_id,))
        conn.commit()
        conn.close()
        return jsonify({"mensaje": "comision eliminada"}), 200
    conn.close()
    return jsonify({"error": "comision no encontrada"}), 404


@app.route("/profesores/<colegio>", methods=["GET"])
def listar_profesores(colegio):
    com = request.args.get("comision")
    conn = get_conn()
    c = conn.cursor()
    if com is None:
        c.execute("""
            SELECT * FROM profesores
            WHERE colegio=? ORDER BY nombre
        """, (colegio,))
    elif com == "__none":
        c.execute("""
            SELECT * FROM profesores
            WHERE colegio=? AND (comision IS NULL OR comision='')
            ORDER BY nombre
        """, (colegio,))
    else:
        c.execute("""
            SELECT * FROM profesores
            WHERE colegio=? AND comision=?
            ORDER BY nombre
        """, (colegio, com))
    arr = []
    for r in c.fetchall():
        item = dict(r)
        try:
            item["extra_campos"] = json.loads(item.get("extra_campos") or "{}")
        except Exception:
            item["extra_campos"] = {}
        arr.append(item)
    conn.close()
    return jsonify({"profesores": arr})


@app.route("/profesores", methods=["POST"])
def crear_profesor():
    data = request.get_json()
    colegio = data.get("colegio")
    nombre = data.get("nombre")
    carnet = data.get("carnet", "")
    cargo = data.get("cargo", "")
    fecha_nac = data.get("fecha_nac", "")
    cel1 = data.get("cel1", "")
    cel2 = data.get("cel2", "")
    cel_extra = data.get("cel_extra", "")
    asesor = data.get("asesor_curso", "")
    comision = data.get("comision", "")
    clases = data.get("clases", "")
    extra_campos = json.dumps(data.get("extra_campos", {}))

    if not colegio or not nombre:
        return jsonify({"error": "faltan datos"}), 400

    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO profesores (colegio, nombre, carnet, cargo, fecha_nac, cel1, cel2, cel_extra,
                                asesor_curso, comision, clases, extra_campos)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (colegio, nombre, carnet, cargo, fecha_nac, cel1, cel2, cel_extra, asesor, comision, clases, extra_campos))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "profesor creado"}), 200


@app.route("/profesores/<int:prof_id>", methods=["PUT"])
def actualizar_profesor(prof_id):
    data = request.get_json()
    campos = ["nombre","carnet","cargo","fecha_nac","cel1","cel2","cel_extra","asesor_curso","comision","clases","extra_campos"]
    sets = []
    valores = []
    for cpo in campos:
        if cpo in data:
            valor = data[cpo]
            if cpo == "extra_campos":
                valor = json.dumps(valor)
            sets.append(f"{cpo}=?")
            valores.append(valor)
    if not sets:
        return jsonify({"error": "nada que actualizar"}), 400
    valores.append(prof_id)
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"UPDATE profesores SET {', '.join(sets)} WHERE id=?", valores)
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "profesor actualizado"}), 200


@app.route("/profesores/<int:prof_id>", methods=["DELETE"])
def eliminar_profesor(prof_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM profesores WHERE id=?", (prof_id,))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "profesor eliminado"}), 200


# --- INICIALIZAR BD AL IMPORTAR ---
init_db()

if __name__ == "__main__":
    # Solo para modo local; Render usará gunicorn app:app
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
