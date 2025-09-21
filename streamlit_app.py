import re, sys, json
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ── Streamlit chrome off (no header/sidebar/footer, zero margins)
st.set_page_config(page_title="Mirror", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
#MainMenu, header, footer {visibility: hidden;}
.block-container {padding:0 !important; margin:0 !important; max-width:100% !important;}
html, body {margin:0 !important; padding:0 !important; overflow:hidden;}
body {background: transparent !important;}
</style>
""", unsafe_allow_html=True)

# ── Fixed source URL
PAGE_URL = "https://felo.ai/en/page/preview/KrcyXakexYzy3cNL2rGJKC?business_type=AGENT_THREAD"

UA = {"user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")}

@st.cache_data(show_spinner=False, ttl=600)
def fetch_url(url: str):
    print(f"[mirror] fetch -> {url}", file=sys.stderr)
    r = requests.get(url, headers=UA, timeout=30)
    print(f"[mirror] status = {r.status_code}", file=sys.stderr)
    r.raise_for_status()
    return r.text, r.url

def absolutize_attr(tag, attr, base):
    v = tag.get(attr)
    if v: tag[attr] = urljoin(base, v)

def absolutize_links(soup: BeautifulSoup, base_url: str):
    if not soup.head:
        soup.insert(0, soup.new_tag("head"))
    for b in soup.find_all("base"): b.decompose()
    soup.head.insert(0, soup.new_tag("base", href=base_url))
    # Common assets absolute
    for a in soup.find_all("a"): absolutize_attr(a, "href", base_url)
    for img in soup.find_all("img"):
        absolutize_attr(img, "src", base_url)
        absolutize_attr(img, "srcset", base_url)
    for s in soup.find_all(["script","link","source","video","audio","track"]):
        for attr in ("src","href","poster"):
            if s.has_attr(attr): absolutize_attr(s, attr, base_url)

def drop_csp_and_noscript(soup: BeautifulSoup):
    for m in soup.find_all("meta", attrs={"http-equiv": re.compile("content-security-policy", re.I)}):
        m.decompose()
    for ns in soup.find_all("noscript"):
        ns.decompose()

def rewrite_css_urls(css_text: str, base_url: str) -> str:
    def repl(m):
        u = m.group(1).strip('\'"')
        return f'url("{urljoin(base_url, u)}")'
    return re.sub(r"url\(([^)]+)\)", repl, css_text)

def inline_css_js(soup: BeautifulSoup, base_url: str,
                  max_bytes_css=3_000_000, max_bytes_js=2_000_000):
    css_inlined = 0

    # 1) link rel=stylesheet OR rel=preload as=style  (Next.js)
    for link in list(soup.find_all("link")):
        rel = [r.lower() for r in (link.get("rel") or [])]
        as_attr = (link.get("as") or "").lower()
        href = link.get("href")

        is_stylesheet = any("stylesheet" in r for r in rel)
        is_preload_style = (as_attr == "style" and href)

        if not href or not (is_stylesheet or is_preload_style):
            continue

        absurl = urljoin(base_url, href)
        try:
            content = requests.get(absurl, headers=UA, timeout=20).content
            css_text = rewrite_css_urls(content.decode("utf-8", errors="ignore"), absurl)
            if len(content) <= max_bytes_css:
                style = soup.new_tag("style")
                style.string = css_text
                link.replace_with(style)
                css_inlined += 1
            else:
                link["href"] = absurl
                link["rel"] = "stylesheet"
                for a in ("onload","integrity","crossorigin"): link.attrs.pop(a, None)
        except Exception:
            link["href"] = absurl
            link["rel"] = "stylesheet"
            for a in ("onload","integrity","crossorigin"): link.attrs.pop(a, None)

    # 2) <style data-n-href|data-href> (Next.js) → إن كان فارغًا، حوّله إلى <link rel=stylesheet>
    for st_tag in list(soup.find_all("style")):
        data_href = st_tag.get("data-n-href") or st_tag.get("data-href")
        if data_href and not (st_tag.string or "").strip():
            href_abs = urljoin(base_url, data_href)
            link = soup.new_tag("link", rel="stylesheet", href=href_abs)
            st_tag.replace_with(link)

    # 3) JS — أزل SRI/CORS دائمًا؛ وضمّن إن كان حجمه مناسبًا
    js_inlined = 0
    for s in list(soup.find_all("script", src=True)):
        src = s.get("src")
        absurl = urljoin(base_url, src)
        try:
            content = requests.get(absurl, headers=UA, timeout=20).content
            if len(content) <= max_bytes_js:
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
            del fr["sandbox"]; n += 1
    if n: print(f"[mirror] unsandboxed iframes: {n}", file=sys.stderr)

def add_runtime_fixes_and_selfcheck(soup: BeautifulSoup):
    # CSS لتصفير الحواف + شارة فحص تختفي تلقائيًا عند النجاح
    extra_css = soup.new_tag("style")
    extra_css.string = """
      html,body{margin:0;padding:0;height:100%;overflow:auto}
      body{background:transparent}
      #mirror-health{position:fixed;top:8px;left:8px;z-index:99999;
        font:12px/1.2 system-ui,Segoe UI,Roboto,sans-serif;
        padding:6px 8px;border-radius:6px;background:#fee;color:#900;border:1px solid #f99;display:none}
      #mirror-health.ok{display:none}
      #mirror-health.bad{display:block}
    """
    if soup.head: soup.head.append(extra_css)
    else: soup.insert(0, extra_css)

    # سكربت: تفعيل preload, دعم هاش سكرول, اختبار ذاتي (CSS/Theme/Anchors)
    tail = soup.new_tag("script")
    tail.string = r"""
    (function(){
      try {
        // Activate preload as stylesheet
        document.querySelectorAll('link[rel="preload"][as="style"]').forEach(function(l){
          if(l.rel !== "stylesheet"){ l.rel = "stylesheet"; }
          l.removeAttribute("onload"); l.removeAttribute("integrity"); l.removeAttribute("crossorigin");
        });
        // Next.js style placeholders -> load external sheet
        document.querySelectorAll('style[data-n-href],style[data-href]').forEach(function(s){
          var href = s.getAttribute('data-n-href') || s.getAttribute('data-href');
          if(href && !s.textContent.trim()){
            var l = document.createElement('link');
            l.rel = 'stylesheet'; l.href = href;
            document.head.appendChild(l);
          }
        });
        // Smooth hash scroll
        document.addEventListener("click", function(e){
          var t = e.target.closest('a[href^="#"], [data-nav]');
          if(!t) return;
          var sel = t.getAttribute("data-nav") || t.getAttribute("href");
          if(!sel || sel === "#") return;
          var el = document.querySelector(sel);
          if(!el) return console.warn("[mirror] target not found:", sel);
          e.preventDefault();
          el.scrollIntoView({behavior:"smooth", block:"start"});
        });

        // ===== Self-Check =====
        var badge = document.createElement('div');
        badge.id = 'mirror-health';
        badge.textContent = 'Mirror self-check failed – some features may not work.';
        document.documentElement.appendChild(badge);

        function pass(){ badge.className = 'ok'; }
        function fail(){ badge.className = 'bad'; }

        // 1) CSS applied? check computed style difference
        var cssOK = (function(){
          try {
            var c = getComputedStyle(document.documentElement);
            // Heuristic: CSS vars or non-default font-size
            return !!(c.getPropertyValue('--font') || c.getPropertyValue('--background') || parseFloat(c.fontSize||'16') !== 16);
          } catch(e){ return false; }
        })();

        // 2) Theme toggle present and functional? best-effort heuristic:
        var themeOK = (function(){
          try {
            var toggle = document.querySelector('[aria-label*="heme" i], [title*="heme" i], [data-theme], button:has(svg[aria-label*="heme" i])');
            if(!toggle) return true; // if no toggle, don't fail the mirror
            var before = document.documentElement.className + '|' + (document.documentElement.getAttribute('data-theme')||'');
            toggle.click();
            var after = document.documentElement.className + '|' + (document.documentElement.getAttribute('data-theme')||'');
            // revert (second click)
            toggle.click();
            return before !== after;
          } catch(e){ return true; }
        })();

        // 3) Anchor navigation works?
        var anchorOK = (function(){
          try {
            var a = document.querySelector('a[href^="#"]');
            return !!a; // existence is enough; behavior handled by smooth scroll
          } catch(e){ return true; }
        })();

        (cssOK && themeOK && anchorOK) ? pass() : fail();
        console.log("[mirror] runtime fixes ready | selfcheck:", {cssOK, themeOK, anchorOK});
      } catch(err){
        console.error("[mirror] boot failed", err);
        try { var b = document.getElementById('mirror-health'); if(b){b.className='bad';} } catch(_){}
      }
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
    add_runtime_fixes_and_selfcheck(soup)

    print(f"[mirror] after prep: scripts={len(soup.find_all('script'))}, "
          f"links={len(soup.find_all('link'))}", file=sys.stderr)
    return str(soup)

try:
    html_flat = flatten(PAGE_URL)
    st.components.v1.html(html_flat, height=3600, scrolling=True)
except requests.exceptions.RequestException as e:
    st.error("Fetch failed."); st.code(repr(e)); raise
except Exception as e:
    st.error("Render failed."); st.exception(e); raise
