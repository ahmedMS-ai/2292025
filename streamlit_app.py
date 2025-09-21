import re
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ــــــــــــــــــــــــــ إعداد صفحة ستريملِت (بدون حواف ولا قوائم) ــــــــــــــــــــــــــ
st.set_page_config(page_title="Mirror", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
/* إخفاء هيدر/فوتر وقائمة ستريملِت وإزالة الحواف */
#MainMenu, header, footer {visibility: hidden;}
.block-container {padding: 0 !important; margin: 0 !important; max-width: 100% !important;}
</style>
""", unsafe_allow_html=True)

# ـــــــــــــــــــــــــــ رابط صفحتك (ثابت كما طلبت) ـــــــــــــــــــــــــــ
PAGE_URL = "https://felo.ai/en/page/preview/KrcyXakexYzy3cNL2rGJKC?business_type=AGENT_THREAD"

# وكيل متصفح بسيط
UA = {"user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")}

@st.cache_data(show_spinner=False, ttl=600)
def fetch_url(url: str):
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    return r.text, r.url  # المحتوى + الرابط النهائي بعد التحويلات

def absolutize_links(soup: BeautifulSoup, base_url: str):
    """أضف <base> واضبط الروابط النسبية لتعمل داخل المكوّن."""
    if not soup.head:
        soup.insert(0, soup.new_tag("head"))
    # احذف أي base قديم ثم أضف واحدًا جديدًا
    for b in soup.find_all("base"):
        b.decompose()
    base = soup.new_tag("base", href=base_url)
    soup.head.insert(0, base)

def drop_csp_and_noscript(soup: BeautifulSoup):
    """أزل قيود CSP ووسوم noscript التي قد تعطل العرض داخل المكوّن."""
    for m in soup.find_all("meta", attrs={"http-equiv": re.compile("content-security-policy", re.I)}):
        m.decompose()
    for ns in soup.find_all("noscript"):
        ns.decompose()

def inline_css_js(soup: BeautifulSoup, base_url: str, max_bytes: int = 400_000):
    """ضمّن الملفات الخفيفة، واجعل البقية مطلقة، وأزل SRI/crossorigin التي قد تمنع التحميل."""
    # CSS
    for link in list(soup.find_all("link", rel=lambda v: v and "stylesheet" in v)):
        href = link.get("href")
        if not href:
            continue
        absurl = urljoin(base_url, href)
        try:
            css = requests.get(absurl, headers=UA, timeout=15).content
            if len(css) <= max_bytes:
                style = soup.new_tag("style")
                style.string = css.decode("utf-8", errors="ignore")
                link.replace_with(style)
            else:
                link["href"] = absurl
        except Exception:
            link["href"] = absurl

    # JS
    for s in list(soup.find_all("script", src=True)):
        src = s.get("src")
        absurl = urljoin(base_url, src)
        try:
            js = requests.get(absurl, headers=UA, timeout=15).content
            if len(js) <= max_bytes:
                new = soup.new_tag("script")
                new.string = js.decode("utf-8", errors="ignore")
                s.replace_with(new)
            else:
                s["src"] = absurl
                s.attrs.pop("integrity", None)
                s.attrs.pop("crossorigin", None)
        except Exception:
            s["src"] = absurl
            s.attrs.pop("integrity", None)
            s.attrs.pop("crossorigin", None)

def unsandbox_iframes(soup: BeautifulSoup):
    """ألغِ sandbox من الإطارات الداخلية إن وُجدت لتعمل محليًا."""
    for fr in soup.find_all("iframe"):
        if fr.has_attr("sandbox"):
            del fr["sandbox"]

def add_quality_of_life_script(soup: BeautifulSoup):
    """سكرول سلس ودعم بسيط للروابط #hash بدون كسر سلوك الصفحة الأصلي."""
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
    if soup.body:
        soup.body.append(tail)
    else:
        soup.append(tail)

def flatten(url: str) -> str:
    """إرجاع HTML جاهز للعرض داخل Streamlit بدون حواف ولا قيود."""
    html, final_url = fetch_url(url)
    soup = BeautifulSoup(html, "lxml")

    # تنظيف وتجهيز
    drop_csp_and_noscript(soup)
    absolutize_links(soup, final_url)
    inline_css_js(soup, final_url)
    unsandbox_iframes(soup)

    # إزالة حواف المتصفح داخل الصفحة نفسها
    extra_css = soup.new_tag("style")
    extra_css.string = "html,body{margin:0;padding:0;}"
    if soup.head: soup.head.append(extra_css)
    else: soup.insert(0, extra_css)

    add_quality_of_life_script(soup)
    return str(soup)

# ـــــــــــــــــــــــــــــــ العرض ـــــــــــــــــــــــــــــــ
try:
    flat_html = flatten(PAGE_URL)
    # نعرض داخل مكوّن HTML واحد بلا أي واجهة إضافية
    st.components.v1.html(flat_html, height=1000, scrolling=True)
except Exception as e:
    st.error("تعذّر عرض الصفحة.")
    st.exception(e)
