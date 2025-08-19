import re
import time
import threading
import webbrowser
from datetime import datetime
from collections import Counter
from urllib.parse import urlparse

import feedparser
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template_string

# Tradução PT-BR
try:
    from deep_translator import GoogleTranslator
    TRANSLATOR = GoogleTranslator(source="auto", target="pt")
except Exception:
    TRANSLATOR = None  # fallback sem tradução

app = Flask(__name__)

# Lista unificada: originais + novos populares
FEEDS = [
    # 🌍 Originais
    "https://feeds.bbci.co.uk/news/rss.xml?edition=int",
    "https://www.theguardian.com/world/rss",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://apnews.com/index.rss",
    "https://neilpatel.com/br/blog/feed/",
    "https://rockcontent.com/br/blog/feed/",
    "https://www.rdstation.com/blog/feed/",
    "https://blog.hubspot.com/marketing/rss.xml",
    "https://contentmarketinginstitute.com/feed/",
    "https://www.archdaily.com.br/br/rss",
    "https://casa.abril.com.br/feed/",
    "https://www.archdaily.com/rss",
    # 🌍 Notícias globais
    "http://feeds.reuters.com/reuters/worldNews",
    "http://rss.cnn.com/rss/edition_world.rss",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada",
    # 💡 Tecnologia
    "http://feeds.feedburner.com/TechCrunch/",
    "https://www.wired.com/feed/rss",
    "https://www.technologyreview.com/feed/",
    # 📈 Negócios
    "https://hbr.org/feed",
    "https://www.forbes.com/business/feed/",
    "https://www.ft.com/rss/world",
]

STOP = set("""
a o os as um uma umas uns de da do das dos e em para por com sem no na nas nos
que como mais menos muito pouco hoje ontem amanhã sobre após antes entre até
ser estar ter fazer poder ir vir já não sim foi são seremos serão
the of to in on for from by with and or is are was were be being been this that
these those as at it its into your our their we you they i he she his her them
an but if then so than just also only new latest veja saiba guia dicas estudo
""".split())

def translate_pt(text: str) -> str:
    if not text:
        return ""
    if TRANSLATOR is None:
        return text
    try:
        if len(text) > 4000:
            chunks, s = [], text
            while s:
                chunks.append(s[:3500]); s = s[3500:]
            return " ".join(TRANSLATOR.translate(c) for c in chunks)
        return TRANSLATOR.translate(text)
    except Exception:
        return text

def clean_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(" ", strip=True)

def top_keywords(text, k=5):
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9-]+", text.lower())
    words = [w for w in words if w not in STOP and len(w) > 2]
    return [w for w, _ in Counter(words).most_common(k)]

def suggest_post(title_pt, summary_pt, link, site_name):
    hashtags = [f"#{k.capitalize()}" for k in top_keywords(title_pt + " " + summary_pt, 3)]
    return (
        f"{title_pt}\n\n"
        f"{summary_pt}\n\n"
        f"Lemos {site_name} e separamos este destaque. O que você acha?\n"
        f"🔗 {link}\n"
        f"{' '.join(hashtags)}"
    )

def site_name_from_url(url):
    return urlparse(url).netloc.replace("www.", "")

def pick_entry(feed):
    return feed.entries[0] if feed.entries else None

def extract_three(entry):
    title = entry.get("title", "").strip()
    summary = clean_html(entry.get("summary", "") or entry.get("description", ""))
    if not summary and "content" in entry and entry["content"]:
        summary = clean_html(entry["content"][0].get("value", ""))

    title_pt = translate_pt(title)
    summary_pt = translate_pt(summary)
    summary_short_pt = (summary_pt[:237] + "...") if len(summary_pt) > 240 else summary_pt
    kw = top_keywords(f"{title_pt} {summary_pt}", 5)
    return title_pt, summary_short_pt, kw

def build_item(feed_url):
    site = site_name_from_url(feed_url)
    try:
        parsed = feedparser.parse(feed_url)
        entry = pick_entry(parsed)
        if not entry:
            return {"site": site, "error": "Sem itens no feed."}
        title_pt, summary_pt, kw = extract_three(entry)
        link = entry.get("link", feed_url)
        post = suggest_post(title_pt, summary_pt, link, site)
        published = entry.get("published") or entry.get("updated") or ""
        published_pt = translate_pt(published) if not re.fullmatch(r"\d{4}.*", published or "") else published
        return {
            "site": site,
            "feed_url": feed_url,
            "published": published_pt,
            "title": title_pt,
            "summary": summary_pt,
            "keywords": kw,
            "link": link,
            "suggested_post": post,
        }
    except Exception as e:
        return {"site": site, "error": str(e)}

CACHE = {"ts": 0, "data": []}
CACHE_TTL = 60 * 10

def refresh_cache():
    data = [build_item(u) for u in FEEDS]
    data = [d for d in data if not (isinstance(d, dict) and d.get("error") == "Sem itens no feed.")]
    CACHE["ts"] = int(time.time())
    CACHE["data"] = data

@app.route("/api")
def api():
    now = int(time.time())
    if now - CACHE["ts"] > CACHE_TTL or not CACHE["data"]:
        refresh_cache()
    return jsonify({
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "items": CACHE["data"]
    })

HTML = """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Feed RSS → Sugestões de Post</title>
  <style>
    :root { --bg:#0f172a; --panel:#111827; --muted:#1f2937; --text:#e2e8f0; --link:#93c5fd; }
    *{box-sizing:border-box}
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu; margin:0; background:var(--bg); color:var(--text)}
    header{padding:24px 16px; text-align:center; background:var(--panel); position:sticky; top:0; z-index:2}
    h1{margin:0 0 8px}
    main{max-width:1000px; margin:24px auto; padding:0 16px}
    .grid{display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:16px}
    .card{background:var(--panel); border:1px solid var(--muted); border-radius:16px; padding:16px}
    .meta{font-size:12px; opacity:.7; margin-bottom:6px}
    .kw{display:inline-block; background:var(--muted); border-radius:999px; padding:4px 8px; margin:2px; font-size:12px}
    a{color:var(--link); text-decoration:none}
    textarea{width:100%; min-height:140px; background:#0b1220; color:var(--text); border:1px solid var(--muted); border-radius:12px; padding:12px}
    .overlay{position:fixed; inset:0; display:none; align-items:center; justify-content:center;
             background:rgba(0,0,0,.35); backdrop-filter:saturate(120%) blur(1px); z-index:5;}
    .overlay.show{ display:flex; }
    .spinner{width:60px; height:60px; border-radius:50%;
             border:6px solid rgba(255,255,255,.25); border-top-color:#60a5fa;
             animation:spin 1s linear infinite; box-shadow:0 0 0 1px rgba(255,255,255,.05) inset;}
    @keyframes spin { to { transform: rotate(360deg); } }
    .error{background:#7f1d1d; border:1px solid #b91c1c; color:#fee2e2; padding:12px; border-radius:12px}
  </style>
</head>
<body>
<header>
  <h1>Feed RSS → Sugestões de Post</h1>
  <div>Atualize esta página para renovar as sugestões (cache de ~10 min)</div>
</header>
<div id="loading" class="overlay" aria-live="polite" aria-busy="true">
  <div class="spinner" role="progressbar" aria-label="Carregando"></div>
</div>
<main>
  <div id="status"></div>
  <div class="grid" id="grid"></div>
</main>
<script>
function showLoading() { document.getElementById('loading').classList.add('show'); }
function hideLoading() { document.getElementById('loading').classList.remove('show'); }

async function load() {
  const grid = document.getElementById('grid');
  const status = document.getElementById('status');
  grid.innerHTML = '';
  status.innerHTML = '';
  showLoading();
  try {
    const r = await fetch('/api', { cache: 'no-store' });
    if (!r.ok) throw new Error('Falha ao buscar dados (' + r.status + ')');
    const j = await r.json();
    if (!Array.isArray(j.items) || j.items.length === 0) {
      status.innerHTML = '<div class="error">Nenhum item disponível no momento. Tente novamente em alguns minutos.</div>';
      return;
    }
    j.items.forEach(it => {
      const div = document.createElement('div');
      div.className = 'card';
      if (it.error){
        div.innerHTML = `<div class="meta">${it.site}</div><strong>Erro</strong>: ${it.error}`;
        grid.appendChild(div);
        return;
      }
      const kws = (it.keywords||[]).map(k=>`<span class="kw">#${k}</span>`).join(' ');
      div.innerHTML = `
        <div class="meta">${it.site} • ${it.published||''}</div>
        <h3 style="margin:6px 0 8px">
          <a href="${it.link}" target="_blank" rel="noopener noreferrer">${it.title}</a>
        </h3>
        <p style="margin:8px 0 12px">${it.summary||''}</p>
        <div style="margin-bottom:12px">${kws}</div>
        <p style="margin:0 0 12px">
          <a href="${it.link}" target="_blank" rel="noopener noreferrer" style="color:#93c5fd; text-decoration:underline;">
            Ler matéria original
          </a>
        </p>
        <label style="font-size:12px;opacity:.75">Sugestão de post</label>
        <textarea readonly>${it.suggested_post}</textarea>
      `;
      grid.appendChild(div);
    });
  } catch (err) {
    status.innerHTML = '<div class="error">Erro ao carregar os feeds: ' + (err?.message || err) + '</div>';
  } finally {
    hideLoading();
  }
}
document.addEventListener('DOMContentLoaded', load);
</script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML)

def _abrir_navegador():
    try:
        webbrowser.open_new("http://127.0.0.1:5000/")
    except Exception:
        pass

if __name__ == "__main__":
    threading.Timer(1.0, _abrir_navegador).start()
    app.run(host="127.0.0.1", port=5000)
