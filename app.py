# -*- coding: utf-8 -*-
# الزوز علامة الملك - منصة الثانوية العامة (ملف واحد)
import os, re, time, json, base64, secrets, sqlite3, urllib.request, urllib.parse
from functools import wraps
from flask import Flask, request, session, redirect, g, render_template_string, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")
DB = os.environ.get("DB_PATH", "zizo.db")
ADMIN = os.environ.get("ADMIN_PHONE", "")          # رقمك انت (ادمن)
YT_KEY = os.environ.get("YT_KEY", "")              # مفتاح YouTube Data API
AI_KEY = os.environ.get("ANTHROPIC_KEY", "")       # مفتاح Claude API
AI_MODEL = os.environ.get("AI_MODEL", "claude-sonnet-5-5")
TW_SID = os.environ.get("TWILIO_SID", "")
TW_TOKEN = os.environ.get("TWILIO_TOKEN", "")
TW_FROM = os.environ.get("TWILIO_FROM", "")

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close(e):
    d = g.pop("db", None)
    if d:
        d.close()

def init():
    c = sqlite3.connect(DB)
    c.executescript("""
    create table if not exists users(phone text primary key, ts int);
    create table if not exists otp(phone text primary key, code text, exp int, tries int default 0);
    create table if not exists books(id integer primary key, title text, grade text, subject text, url text);
    create table if not exists posts(id integer primary key, phone text, title text, body text, ts int);
    create table if not exists replies(id integer primary key, post int, phone text, body text, ts int);
    """)
    c.commit(); c.close()
init()

BASE = """<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>الزوز 👑</title>
<style>
:root{--bg:#0b1437;--card:#141f4d;--gold:#f5c542;--tx:#eef1ff;--mut:#9aa6d6}
*{box-sizing:border-box}body{margin:0;font-family:Tahoma,Arial,sans-serif;background:linear-gradient(160deg,#0b1437,#1b2a6b);color:var(--tx);min-height:100vh}
header{display:flex;justify-content:space-between;align-items:center;padding:14px 18px;background:#0008;position:sticky;top:0;z-index:5}
header a{color:var(--gold);text-decoration:none;font-weight:bold;font-size:18px}header a.s{font-size:14px;color:var(--mut)}
main{max-width:900px;margin:auto;padding:16px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.tile{background:var(--card);border:1px solid #ffffff22;border-radius:18px;padding:22px 10px;text-align:center;color:var(--tx);text-decoration:none;font-size:17px;box-shadow:0 6px 18px #0006}
.tile b{display:block;font-size:34px;margin-bottom:6px}
.card{background:var(--card);border-radius:16px;padding:14px;margin:10px 0;border:1px solid #ffffff18}
h1,h2{color:var(--gold)}
input,select,textarea{width:100%;padding:12px;border-radius:12px;border:1px solid #ffffff33;background:#0b143788;color:var(--tx);font-size:16px;margin:6px 0;font-family:inherit}
button,.btn{background:var(--gold);color:#222;border:0;border-radius:12px;padding:12px 18px;font-size:16px;font-weight:bold;cursor:pointer;text-decoration:none;display:inline-block}
.msg{background:#f5c54222;border:1px solid var(--gold);padding:10px;border-radius:10px;margin:8px 0}
a{color:var(--gold)}small,.mut{color:var(--mut)}
.vid{display:flex;gap:10px;align-items:center;cursor:pointer}.vid img{width:120px;border-radius:10px}
iframe{width:100%;aspect-ratio:16/9;border:0;border-radius:14px}
.me{background:#f5c54233;margin-right:30px}.bot{background:#ffffff14;margin-left:30px}
</style></head><body>
<header><a href="/">👑 الزوز علامة الملك</a>{% if me %}<a class="s" href="/logout">خروج</a>{% endif %}</header>
<main>{{ body|safe }}</main></body></html>"""

def page(tpl, **kw):
    body = render_template_string(tpl, **kw)
    return render_template_string(BASE, body=body, me=session.get("phone"))

def need_login(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("phone"):
            return redirect("/login")
        return f(*a, **k)
    return w

def is_admin():
    return ADMIN and session.get("phone") == ADMIN

def norm(s):
    d = re.sub(r"\D", "", s or "")
    d = d.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")) if d else d
    if d.startswith("20") and len(d) == 12:
        d = "0" + d[2:]
    return d if re.fullmatch(r"01[0125]\d{8}", d) else None

def send_sms(phone, code):
    if not (TW_SID and TW_TOKEN and TW_FROM):
        return False
    try:
        data = urllib.parse.urlencode({"To": "+20" + phone[1:], "From": TW_FROM,
                                       "Body": "كود الدخول لمنصة الزوز: " + code}).encode()
        r = urllib.request.Request("https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json" % TW_SID, data=data)
        r.add_header("Authorization", "Basic " + base64.b64encode((TW_SID + ":" + TW_TOKEN).encode()).decode())
        urllib.request.urlopen(r, timeout=15)
        return True
    except Exception:
        return False

# ---------- الدخول ----------
LOGIN = """<h1>تسجيل الدخول 👑</h1><div class="card">
{% if msg %}<div class="msg">{{ msg }}</div>{% endif %}
<form method="post"><label>رقم موبايلك</label>
<input name="phone" inputmode="tel" placeholder="01XXXXXXXXX" required>
<button>ابعتلي الكود</button></form></div>"""

VERIFY = """<h1>اكتب الكود</h1><div class="card">
{% if demo %}<div class="msg">وضع تجريبي (الـSMS مش متفعل): الكود هو <b>{{ demo }}</b></div>{% endif %}
{% if msg %}<div class="msg">{{ msg }}</div>{% endif %}
<form method="post"><input name="code" inputmode="numeric" placeholder="الكود (6 أرقام)" required>
<button>دخول</button></form></div>"""

@app.route("/login", methods=["GET", "POST"])
def login():
    msg = ""
    if request.method == "POST":
        p = norm(request.form.get("phone"))
        if not p:
            msg = "الرقم غلط، اكتبه زي 01012345678"
        else:
            r = db().execute("select exp from otp where phone=?", (p,)).fetchone()
            if r and r["exp"] - 240 > time.time():
                msg = "استنى دقيقة وجرب تاني"
            else:
                code = str(secrets.randbelow(900000) + 100000)
                db().execute("insert or replace into otp values(?,?,?,0)", (p, code, int(time.time()) + 300))
                db().commit()
                session["pending"] = p
                session["demo"] = "" if send_sms(p, code) else code
                return redirect("/verify")
    return page(LOGIN, msg=msg)

@app.route("/verify", methods=["GET", "POST"])
def verify():
    p = session.get("pending")
    if not p:
        return redirect("/login")
    msg = ""
    if request.method == "POST":
        r = db().execute("select * from otp where phone=?", (p,)).fetchone()
        if not r or r["exp"] < time.time() or r["tries"] >= 5:
            msg = "الكود انتهى، اطلب كود جديد"
        elif request.form.get("code", "").strip() == r["code"]:
            db().execute("delete from otp where phone=?", (p,))
            db().execute("insert or ignore into users values(?,?)", (p, int(time.time())))
            db().commit()
            session.clear(); session["phone"] = p
            return redirect("/")
        else:
            db().execute("update otp set tries=tries+1 where phone=?", (p,)); db().commit()
            msg = "الكود غلط"
    return page(VERIFY, msg=msg, demo=session.get("demo"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------- الرئيسية ----------
HOME = """<h1>أهلاً بيك 👑</h1><p class="mut">كل اللي محتاجه للثانوية في مكان واحد</p>
<div class="grid">
<a class="tile" href="/books"><b>📚</b>الكتب</a>
<a class="tile" href="/lectures"><b>🎬</b>المحاضرات</a>
<a class="tile" href="/forum"><b>💬</b>منتدى الطلاب</a>
<a class="tile" href="/tips"><b>💡</b>إرشادات ونصائح</a>
<a class="tile" href="/ai" style="grid-column:span 2"><b>🤖</b>المساعد الذكي</a></div>"""

@app.route("/")
@need_login
def home():
    return page(HOME)

# ---------- الكتب ----------
BOOKS = """<h1>📚 الكتب</h1>
<form method="get"><select name="grade" onchange="this.form.submit()">
<option value="">كل الصفوف</option>
{% for g in grades %}<option {{ 'selected' if g==sel }}>{{ g }}</option>{% endfor %}</select></form>
{% for b in books %}<div class="card"><b>{{ b.title }}</b><br><small>{{ b.grade }} - {{ b.subject }}</small><br><br>
<a class="btn" href="{{ b.url }}" target="_blank" rel="noopener">فتح الكتاب</a>
{% if admin %}<a href="/books/del/{{ b.id }}" style="margin-right:12px">حذف</a>{% endif %}</div>
{% else %}<div class="card">مفيش كتب لسه.</div>{% endfor %}
{% if admin %}<div class="card"><h2>إضافة كتاب (ادمن)</h2><form method="post">
<input name="title" placeholder="اسم الكتاب" required>
<select name="grade">{% for g in grades %}<option>{{ g }}</option>{% endfor %}</select>
<input name="subject" placeholder="المادة" required>
<input name="url" placeholder="رابط الكتاب (PDF)" required><button>إضافة</button></form></div>{% endif %}"""
GRADES = ["أولى ثانوي", "تانية ثانوي", "تالتة ثانوي"]

@app.route("/books", methods=["GET", "POST"])
@need_login
def books():
    if request.method == "POST" and is_admin():
        f = request.form
        if f.get("url", "").startswith("http"):
            db().execute("insert into books(title,grade,subject,url) values(?,?,?,?)",
                         (f["title"], f["grade"], f["subject"], f["url"]))
            db().commit()
        return redirect("/books")
    sel = request.args.get("grade", "")
    q = "select * from books" + (" where grade=?" if sel else "") + " order by id desc"
    rows = db().execute(q, (sel,) if sel else ()).fetchall()
    return page(BOOKS, books=rows, grades=GRADES, sel=sel, admin=is_admin())

@app.route("/books/del/<int:i>")
@need_login
def bdel(i):
    if is_admin():
        db().execute("delete from books where id=?", (i,)); db().commit()
    return redirect("/books")

# ---------- المحاضرات ----------
LEC = """<h1>🎬 المحاضرات</h1>
<form method="get"><input name="q" value="{{ q }}" placeholder="ابحث: مادة، مدرس، درس..."><button>بحث</button></form>
<div id="pl"></div>
{% if note %}<div class="msg">{{ note }}</div>{% endif %}
{% for v in vids %}<div class="card vid" onclick="play('{{ v.id }}')"><img src="{{ v.img }}"><div>{{ v.title }}<br><small>{{ v.ch }}</small></div></div>{% endfor %}
{% if q %}<a class="btn" target="_blank" href="https://www.youtube.com/results?search_query={{ q|urlencode }}">افتح البحث في يوتيوب</a>{% endif %}
<script>function play(i){document.getElementById('pl').innerHTML='<iframe src="https://www.youtube.com/embed/'+i+'?autoplay=1" allow="autoplay;fullscreen" allowfullscreen></iframe>';scrollTo(0,0)}</script>"""

@app.route("/lectures")
@need_login
def lectures():
    q = request.args.get("q", "").strip()
    vids, note = [], ""
    if q and YT_KEY:
        try:
            u = "https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(
                {"part": "snippet", "type": "video", "maxResults": 12, "q": q + " ثانوية عامة شرح",
                 "key": YT_KEY, "relevanceLanguage": "ar"})
            d = json.loads(urllib.request.urlopen(u, timeout=15).read())
            for it in d.get("items", []):
                s = it["snippet"]
                vids.append({"id": it["id"]["videoId"], "title": s["title"], "ch": s["channelTitle"],
                             "img": s["thumbnails"]["medium"]["url"]})
        except Exception:
            note = "حصلت مشكلة في البحث، جرب تاني."
    elif q:
        note = "البحث المباشر لسه مش متفعل (محتاج YT_KEY)، استخدم زرار يوتيوب تحت."
    return page(LEC, q=q, vids=vids, note=note)

# ---------- المنتدى ----------
FORUM = """<h1>💬 منتدى الطلاب</h1>
<div class="card"><form method="post"><input name="title" placeholder="عنوان سؤالك" required>
<textarea name="body" rows="3" placeholder="اكتب سؤالك..." required></textarea><button>نشر</button></form></div>
{% for p in posts %}<a href="/forum/{{ p.id }}" style="text-decoration:none;color:inherit"><div class="card"><b>{{ p.title }}</b><br>
<small>***{{ p.phone[-3:] }} - {{ p.n }} رد</small></div></a>{% endfor %}"""
POST = """<a href="/forum">← رجوع</a><div class="card"><h2>{{ p.title }}</h2><p>{{ p.body }}</p><small>***{{ p.phone[-3:] }}</small></div>
{% for r in rs %}<div class="card">{{ r.body }}<br><small>***{{ r.phone[-3:] }}</small></div>{% endfor %}
<div class="card"><form method="post"><textarea name="body" rows="3" placeholder="اكتب ردك" required></textarea><button>رد</button></form></div>"""

@app.route("/forum", methods=["GET", "POST"])
@need_login
def forum():
    if request.method == "POST":
        t, b = request.form.get("title", "").strip()[:150], request.form.get("body", "").strip()[:2000]
        if t and b:
            db().execute("insert into posts(phone,title,body,ts) values(?,?,?,?)", (session["phone"], t, b, int(time.time())))
            db().commit()
        return redirect("/forum")
    rows = db().execute("select p.*,(select count(*) from replies where post=p.id) n from posts p order by id desc limit 50").fetchall()
    return page(FORUM, posts=rows)

@app.route("/forum/<int:i>", methods=["GET", "POST"])
@need_login
def post(i):
    p = db().execute("select * from posts where id=?", (i,)).fetchone()
    if not p:
        return redirect("/forum")
    if request.method == "POST":
        b = request.form.get("body", "").strip()[:2000]
        if b:
            db().execute("insert into replies(post,phone,body,ts) values(?,?,?,?)", (i, session["phone"], b, int(time.time())))
            db().commit()
        return redirect("/forum/%d" % i)
    rs = db().execute("select * from replies where post=? order by id", (i,)).fetchall()
    return page(POST, p=p, rs=rs)

# ---------- نصائح ----------
TIPS = """<h1>💡 إرشادات ونصائح</h1>
<div class="card"><b>⏰ نظم وقتك</b><br>جدول يومي ثابت، ومذاكرة 45 دقيقة وراحة 10.</div>
<div class="card"><b>📝 حل امتحانات</b><br>حل امتحانات السنين اللي فاتت بتوقيت حقيقي.</div>
<div class="card"><b>😴 نوم كويس</b><br>7 ساعات نوم أحسن من سهر قبل الامتحان.</div>
<div class="card"><b>🔁 راجع بانتظام</b><br>مراجعة قصيرة كل أسبوع أحسن من تلتميت ساعة في الآخر.</div>
<div class="card"><b>📵 قلل الموبايل</b><br>اقفل الإشعارات وقت المذاكرة.</div>
<div class="card"><b>🧠 اسأل لما متفهمش</b><br>اسأل في المنتدى أو المساعد الذكي بدل ما تحفظ من غير فهم.</div>"""

@app.route("/tips")
@need_login
def tips():
    return page(TIPS)

# ---------- المساعد الذكي ----------
AIP = """<h1>🤖 المساعد الذكي</h1><div id="chat"><div class="card bot">أهلاً! اسألني في أي مادة ثانوي 👑</div></div>
<div class="card"><textarea id="q" rows="2" placeholder="اكتب سؤالك..."></textarea><button onclick="ask()">إرسال</button></div>
<script>
async function ask(){var q=document.getElementById('q'),c=document.getElementById('chat'),t=q.value.trim();if(!t)return;
c.insertAdjacentHTML('beforeend','<div class="card me"></div>');c.lastChild.textContent=t;q.value='';
c.insertAdjacentHTML('beforeend','<div class="card bot">...</div>');var b=c.lastChild;
try{var r=await fetch('/api/ai',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q:t})});
var d=await r.json();b.style.whiteSpace='pre-wrap';b.textContent=d.a}catch(e){b.textContent='حصلت مشكلة، جرب تاني'}}
</script>"""

@app.route("/ai")
@need_login
def ai():
    return page(AIP)

@app.route("/api/ai", methods=["POST"])
@need_login
def api_ai():
    q = (request.get_json(silent=True) or {}).get("q", "")[:2000]
    if not AI_KEY:
        return jsonify(a="المساعد لسه مش متفعل (محتاج ANTHROPIC_KEY).")
    try:
        body = json.dumps({"model": AI_MODEL, "max_tokens": 800,
            "system": "انت مساعد دراسي لطلاب الثانوية العامة في مصر. اشرح ببساطة وباللهجة المصرية وبخطوات واضحة.",
            "messages": [{"role": "user", "content": q}]}).encode()
        r = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body)
        r.add_header("x-api-key", AI_KEY); r.add_header("anthropic-version", "2023-06-01")
        r.add_header("content-type", "application/json")
        d = json.loads(urllib.request.urlopen(r, timeout=40).read())
        return jsonify(a="".join(x.get("text", "") for x in d["content"]))
    except Exception:
        return jsonify(a="مقدرتش أرد دلوقتي، جرب بعد شوية.")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
