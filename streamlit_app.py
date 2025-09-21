import re, sys
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ===== Streamlit page: no chrome, no margins =====
st.set_page_config(page_title="Mirror", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
#MainMenu, header, footer {visibility: hidden;}
.block-container {padding:0 !important; margin:0 !important; max-width:100% !important;}
html, body {margin:0 !important; padding:0 !important; overflow:hidden;}
body {background: transparent !important;}
</style>
""", unsafe_allow_html=True)

# ===== ثابت: رابط صفحتك =====
PAGE_URL = "https://felo.ai/en/page/preview/KrcyXakexYzy3cNL2rGJKC?business_type=AGENT_THREAD"

# ===== HTTP settings =====
UA = {"user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")}

@st.cache_data(show_spinner=False, ttl=600)
def fetch_url(url: str):
    print(f"[mirror] fetch -> {url}", file=sys.stderr)
    r = requests.get(url, headers=UA, timeout=25)
    print(f"[mirror] status = {r.status_code}", file=sys.stderr)
    r.raise_for_status()
    return r.text, r.url  # html + final URL (after redirects)

def absolutize_links(soup: BeautifulSoup, base_url: str):
    if not soup.head:
        soup.insert(0, soup.new_tag("head"))
    for b in soup.find_all("base"):
        b.decompose()
    base = soup.new_tag("base", href=base_url)
    soup.head.insert(0, base)

def drop_csp_and_noscript(soup: BeautifulSoup):
    for m in soup.find_all("meta", attrs={"http-equiv": re.compile("content-security-policy", re.I)}):
        m.decompose()
    for ns in soup.find_all("noscript"):
        ns.decompose()

def inline_css_js(soup: BeautifulSoup, base_url: str, max_bytes: int = 500_000):
    # CSS
    css_inlined = 0
    for link in list(soup.find_all("link", rel=lambda v: v and "stylesheet" in v)):
        href = link.get("href")
        if not href:
            continue
        absurl = urljoin(base_url, href)
        try:
            content = requests.get(absurl, headers=UA, timeout=15).content
            if len(content) <= max_bytes:
                style = soup.new_tag("style")
                style.string = content.decode("utf-8", errors="ignore")
                link.replace_with(style)
                css_inlined += 1
            else:
                link["href"] = absurl
        except Exception:
            link["href"] = absurl
    # JS
    js_inlined = 0
    for s in list(soup.find_all("script", src=True)):
        src = s.get("src")
        absurl = urljoin(base_url, src)
        try:
            content = requests.get(absurl, headers=UA, timeout=15).content
            if len(content) <= max_bytes:
                new = soup.new_tag("script")
                new.string = content.decode("utf-8", errors="ignore")
                s.replace_with(new)
                js_inlined += 1
            else:
                s["src"] = absurl
                s.attrs.pop("integrity", None)
                s.attrs.pop("crossorigin", None)
        except Exception:
            s["src"] = absurl
            s.attrs.pop("integrity", None)
            s.attrs.pop("crossorigin", None)

    print(f"[mirror] inlined: css={css_inlined}, js={js_inlined}", file=sys.stderr)

def unsandbox_iframes(soup: BeautifulSoup):
    n = 0
    for fr in soup.find_all("iframe"):
        if fr.has_attr("sandbox"):
            del fr["sandbox"]
            n += 1
    if n:
        print(f"[mirror] unsandboxed iframes: {n}", file=sys.stderr)

def add_qol_script_and_css(soup: BeautifulSoup):
    extra_css = soup.new_tag("style")
    extra_css.string = "html,body{margin:0;padding:0;height:100%;overflow:auto} body{background:transparent}"
    if soup.head: soup.head.append(extra_css)
    else: soup.insert(0, extra_css)

    tail = soup.new_tag("script")
    tail.string = """
    (function(){
      try {
        document.addEventListener("click", function(e){
          const t = e.target.closest('a[href^="#"], [data-nav]');
          if(!t) return;
          const sel = t.getAttribute("data-nav") || t.getAttribute("href");
          if(!sel || sel === "#") return;
          const el = document.querySelector(sel);
          if(!el) return console.warn("[mirror] target not found:", sel);
          e.preventDefault();
          el.scrollIntoView({behavior:"smooth", block:"start"});
        });
        console.log("[mirror] ready");
      } catch(err){ console.error("[mirror] boot failed", err); }
    })();
    """
    if soup.body: soup.body.append(tail)
    else: soup.append(tail)

def flatten(url: str) -> str:
    html, final_url = fetch_url(url)
    print(f"[mirror] final_url = {final_url}, size={len(html)} bytes", file=sys.stderr)
    soup = BeautifulSoup(html, "lxml")

    drop_csp_and_noscript(soup)
    absolutize_links(soup, final_url)
    inline_css_js(soup, final_url)
    unsandbox_iframes(soup)

    add_qol_script_and_css(soup)

    # إحصائيات بسيطة
    n_scripts = len(soup.find_all("script"))
    n_links   = len(soup.find_all("link"))
    print(f"[mirror] after prep: scripts={n_scripts}, links={n_links}", file=sys.stderr)

    return str(soup)

# ===== Render (no controls) =====
try:
    html_flat = flatten(PAGE_URL)
    st.components.v1.html(html_flat, height=1800, scrolling=True)
except requests.exceptions.RequestException as e:
    st.error("فشل في جلب الصفحة من المصدر.")
    st.code(repr(e))
    raise
except Exception as e:
    st.error("تعذّر عرض الصفحة.")
    st.exception(e)
    raise
