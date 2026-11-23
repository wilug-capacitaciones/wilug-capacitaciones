import os, io, re, secrets, hmac
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, request, session, redirect, url_for, render_template_string, abort, send_file
from sqlalchemy import create_engine, text
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape, A4
from openpyxl import Workbook
import qrcode

if not os.getenv("SECRET_KEY") or not os.getenv("ADMIN_PASSWORD"):
    raise RuntimeError("Configure SECRET_KEY and ADMIN_PASSWORD before starting")
app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "1") == "1", MAX_CONTENT_LENGTH=120000)
dburl = os.getenv("DATABASE_URL", "sqlite:///wilug.db")
if dburl.startswith("postgres://"): dburl = "postgresql+psycopg://" + dburl[11:]
elif dburl.startswith("postgresql://"): dburl = "postgresql+psycopg://" + dburl[13:]
engine = create_engine(dburl, pool_pre_ping=True)
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE IF NOT EXISTS attempts (id VARCHAR(40) PRIMARY KEY, name VARCHAR(160), rut VARCHAR(20), company VARCHAR(160), score INTEGER, created_at VARCHAR(40))"))

# Technical questions require instructor review before real use.
RAW = [
("¿Qué debe hacerse primero al detectar un incendio?","Avisar y activar la alarma","Buscar un extintor sin avisar","Abrir puertas",0),
("¿Qué es un fuego clase A?","Líquidos inflamables","Sólidos combustibles comunes","Metales combustibles",1),
("¿Qué es un fuego clase B?","Líquidos inflamables","Papel","Aceites de cocina",0),
("¿Qué es un fuego clase C en Chile?","Madera","Metales","Equipos eléctricos energizados",2),
("¿Qué es un fuego clase D?","Metales combustibles","Cartón","Equipos energizados",0),
("¿Qué es un fuego clase K?","Papel","Aceites y grasas de cocina","Metales",1),
("¿A dónde se dirige el agente extintor?","Al humo","A la base del fuego","A la parte alta de las llamas",1),
("¿Cuándo es adecuado intentar usar un extintor?","Cuando hay una salida segura, capacitación y fuego incipiente","Siempre","Cuando el fuego bloquea la salida",0),
("¿Dónde debe mantenerse la vía de escape?","Detrás del incendio","Bloqueada","Libre y disponible",2),
("¿Qué hacer si el fuego aumenta?","Seguir hasta vaciar el equipo","Retirarse y seguir el plan de emergencia","Acercarse",1),
("¿Qué indica un manómetro fuera de rango?","Equipo requiere revisión según procedimiento","Equipo listo","Equipo nuevo",0),
("¿Qué revisar antes de usar un extintor?","Solo el color","Solo el soporte","Estado físico, seguro, sello e indicaciones",2),
("¿Qué hacer con un extintor usado parcialmente?","Devolverlo sin informar","Informar y gestionar revisión o recarga","Guardarlo",1),
("¿Qué agente es común en extintores ABC?","Polvo químico seco ABC","Solo agua","Arena",0),
("¿Se debe aplicar agua a equipos eléctricos energizados?","Siempre","Solo si hay humo","No, salvo procedimientos y equipos autorizados",2),
("¿Qué riesgo implica usar un agente inadecuado?","Ninguno","Agravamiento del incendio u otros peligros","Solo cambia el humo",1),
("¿Por qué conocer el alcance y tiempo de descarga?","Para mantener distancia y planificar el ataque","Para decorar la etiqueta","Para omitir la alarma",0),
("¿Qué debe hacer alguien sin capacitación?","Atacar el fuego","Entrar a investigar","Alertar y evacuar según el plan",2),
("¿Qué hacer después de una intervención?","Ocultar el extintor","Informar y gestionar reposición","Retirar señalización",1),
("¿Qué es prioritario ante un incendio?","La seguridad de las personas","Salvar equipos a cualquier costo","Evitar avisar",0)]
STYLE = "<meta name='viewport' content='width=device-width,initial-scale=1'><style>body{font:16px system-ui;background:#f3f6fa;color:#16283b;margin:0}main{max-width:760px;margin:28px auto;background:white;padding:24px;border-radius:16px}input,button{font:inherit;padding:10px;margin:5px 0}input[type=text],input[type=password]{width:95%}fieldset{margin:15px 0;border:1px solid #d8dfe6;border-radius:8px}button,.btn{background:#154b75;color:white;border:0;border-radius:8px;padding:12px;display:inline-block;text-decoration:none}a{color:#154b75}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:8px;text-align:left}</style>"
def page(body, **data): return render_template_string(STYLE + "<main><h1>WILUG · Capacitación en extintores</h1>" + body + "</main>", **data)
def csrf(): return session.setdefault("csrf", secrets.token_urlsafe(24))
def verify_csrf():
    if not hmac.compare_digest(request.form.get("csrf",""),session.get("csrf","")): abort(403)
def rut_valid(value):
    s = re.sub(r"[^0-9kK]","",value).upper()
    if len(s)<8 or len(s)>10 or not s[:-1].isdigit(): return False
    total=sum(int(d)*[2,3,4,5,6,7][i%6] for i,d in enumerate(reversed(s[:-1])))
    check=11-total%11
    return s[-1]==("0" if check==11 else "K" if check==10 else str(check))
def admin_only(f):
    @wraps(f)
    def inner(*a,**kw):
        if not session.get("admin"): return redirect(url_for("login"))
        return f(*a,**kw)
    return inner
def get_attempt(ident):
    with engine.connect() as c: return c.execute(text("SELECT * FROM attempts WHERE id=:id"),{"id":ident}).mappings().first()
@app.get("/")
def home():
    return page("""<p>Evaluación de 20 preguntas. Aprobación mínima: 14 correctas (70%).</p><form method="post" action="/submit"><input type="hidden" name="csrf" value="{{token}}"><label>Nombre completo<input type="text" name="name" maxlength="160" required></label><label>RUT<input type="text" name="rut" maxlength="20" required></label><label>Empresa<input type="text" name="company" maxlength="160" required></label>{% for q in questions %}<fieldset><legend>{{loop.index}}. {{q[0]}}</legend>{% set idx=loop.index0 %}{% for option in q[1:4] %}<label><input type="radio" name="q{{idx}}" value="{{loop.index0}}" required> {{option}}</label><br>{% endfor %}</fieldset>{% endfor %}<button>Enviar evaluación</button></form>""",token=csrf(),questions=RAW)
@app.post("/submit")
def submit():
    verify_csrf()
    name=request.form.get("name","").strip(); rut=request.form.get("rut","").strip(); company=request.form.get("company","").strip()
    if not (2<=len(name)<=160 and rut_valid(rut) and 2<=len(company)<=160): return "Datos inválidos: revisa nombre, RUT y empresa.",400
    answers=[request.form.get("q"+str(i)) for i in range(20)]
    if any(a not in ("0","1","2") for a in answers): return "Responde todas las preguntas.",400
    score=sum(int(a)==q[4] for a,q in zip(answers,RAW))
    ident=secrets.token_hex(16)
    with engine.begin() as c:
        c.execute(text("INSERT INTO attempts(id,name,rut,company,score,created_at) VALUES(:id,:name,:rut,:company,:score,:date)"),{"id":ident,"name":name,"rut":rut,"company":company,"score":score,"date":datetime.now(timezone.utc).isoformat()})
    session["attempt"]=ident
    return redirect(url_for("result",ident=ident))
@app.get("/resultado/<ident>")
def result(ident):
    if session.get("attempt")!=ident and not session.get("admin"): abort(403)
    r=get_attempt(ident)
    if not r: abort(404)
    return page("""<h2>{{r.name}}</h2><p>Resultado: <b>{{r.score}}/20 ({{r.score*5}}%)</b></p>{% if r.score>=14 %}<p>APROBADO</p><a class="btn" href="{{url_for('diploma',ident=r.id)}}">Descargar diploma PDF</a>{% else %}<p>NO APROBADO. Se requiere reforzamiento.</p>{% endif %}""",r=r)
@app.get("/diploma/<ident>.pdf")
def diploma(ident):
    if session.get("attempt")!=ident and not session.get("admin"): abort(403)
    r=get_attempt(ident)
    if not r: abort(404)
    if r["score"]<14: abort(403)
    buf=io.BytesIO(); w,h=landscape(A4); pdf=canvas.Canvas(buf,pagesize=(w,h))
    pdf.setStrokeColorRGB(.08,.27,.46);pdf.setLineWidth(4);pdf.rect(24,24,w-48,h-48)
    for y,size,s in [(h-110,26,"WILUG"),(h-170,22,"DIPLOMA DE APROBACIÓN"),(h-215,15,"Curso: Uso y Manejo de Extintores"),(h-270,19,r["name"][:60]),(h-305,12,"RUT: "+r["rut"]+" | Empresa: "+r["company"][:40]),(h-345,13,f"Resultado: {r['score']}/20 ({r['score']*5}%)"),(110,10,"Certificado: WILUG-"+r["id"][:12].upper()),(85,10,"Pendiente de validación y firma institucional")]:
        pdf.setFont("Helvetica",size);pdf.drawCentredString(w/2,y,s.replace("Ó","O"))
    pdf.showPage();pdf.save();buf.seek(0)
    return send_file(buf,mimetype="application/pdf",as_attachment=True,download_name="Diploma_WILUG.pdf")
@app.route("/admin/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        verify_csrf()
        if hmac.compare_digest(request.form.get("password",""),os.environ["ADMIN_PASSWORD"]):
            session.clear();session["admin"]=True;return redirect(url_for("admin"))
        return "Credenciales incorrectas",403
    return page('<form method="post"><input type="hidden" name="csrf" value="{{token}}"><input type="password" name="password" required><button>Ingresar</button></form>',token=csrf())
@app.post("/admin/logout")
@admin_only
def logout():
    verify_csrf();session.clear();return redirect(url_for("home"))
@app.get("/admin")
@admin_only
def admin():
    with engine.connect() as c: rows=c.execute(text("SELECT * FROM attempts ORDER BY created_at DESC")).mappings().all()
    return page("""<p>Participantes: {{rows|length}} · Aprobados: {{rows|selectattr('score','ge',14)|list|length}}</p><p><a href="/admin/resultados.xlsx">Descargar Excel</a> · <a href="/admin/qr.png">Descargar QR</a></p><form method="post" action="/admin/logout"><input type="hidden" name="csrf" value="{{token}}"><button>Salir</button></form><div style="overflow-x:auto"><table><tr><th>Nombre</th><th>RUT</th><th>Empresa</th><th>Correctas</th><th>Fecha UTC</th></tr>{% for r in rows %}<tr><td>{{r.name}}</td><td>{{r.rut}}</td><td>{{r.company}}</td><td>{{r.score}}/20</td><td>{{r.created_at}}</td></tr>{% endfor %}</table></div>""",rows=rows,token=csrf())
@app.get("/admin/resultados.xlsx")
@admin_only
def excel():
    wb=Workbook();ws=wb.active;ws.title="Resultados";ws.append(["Certificado","Nombre","RUT","Empresa","Correctas","Porcentaje","Estado","Fecha UTC"])
    with engine.connect() as c: rows=c.execute(text("SELECT * FROM attempts ORDER BY created_at DESC")).mappings().all()
    for r in rows:
        safe=lambda s: "'"+s if str(s).startswith(("=","+","-","@")) else s
        ws.append(["WILUG-"+r["id"][:12].upper() if r["score"]>=14 else "",safe(r["name"]),safe(r["rut"]),safe(r["company"]),r["score"],r["score"]*5,"APROBADO" if r["score"]>=14 else "REPROBADO",r["created_at"]])
    buf=io.BytesIO();wb.save(buf);buf.seek(0)
    return send_file(buf,mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",as_attachment=True,download_name="Resultados_WILUG.xlsx")
@app.get("/admin/qr.png")
@admin_only
def qr():
    url=os.getenv("PUBLIC_URL",request.url_root).rstrip("/")+"/"
    img=qrcode.make(url);buf=io.BytesIO();img.save(buf,format="PNG");buf.seek(0)
    return send_file(buf,mimetype="image/png",as_attachment=True,download_name="QR_WILUG.png")
@app.get("/health")
def health(): return {"status":"ok"}
