import re
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import urljoin

st.set_page_config(page_title="Page Mirror", layout="wide")

UA = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

@st.cache_data(show_spinner=False, ttl=600)
def fetch_url(url: str):
    r = requests.get(url, headers=UA, timeout=20)
    r.raise_for_status()
    return r.text, r.url  # content + final URL after redirects

def absolutize_links(soup: BeautifulSoup, base_url: str):
    # حط <base> عشان الروابط النسبية تتصرف صح
    if not soup.head:
        soup.insert(0, soup.new_tag("head"))
    # احذف أي base قديم
    for b in soup.find_all("base"):
        b.decompose()
    base = soup.new_tag("base", href=base_url)
    soup.head.insert(0, base)

def drop_csp_and_noscript(soup: BeautifulSoup):
    # امسح قيود الأمان اللي تمنع تشغيل سكربت داخل المكوّن
    for m in soup.find_all("meta", attrs={"http-equiv": re.compile("content-security-policy", re.I)}):
        m.decompose()
    # صفحات كتير تستخدم noscript يبوّز الشكل داخل iframe/inline
    for ns in soup.find_all("noscript"):
        ns.decompose()

def inline_css_js(soup: BeautifulSoup, base_url: str, max_bytes: int = 400_000):
    """نحاول نضمّن CSS/JS الخارجي (لو حجمه معقول)."""
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
                # خلّيها مطلقة بدل نسبية
                link["href"] = absurl
        except Exception:
            # فشل؟ خلّيها مطلقة
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
                # إزالة SRI قد تمنع التحميل عبر origin مختلف
                s.attrs.pop("integrity", None)
                s.attrs.pop("crossorigin", None)
        except Exception:
            s["src"] = absurl
            s.attrs.pop("integrity", None)
            s.attrs.pop("crossorigin", None)

def unsandbox_iframes(soup: BeautifulSoup):
    # لو في iframes داخل الصفحة، شيل sandbox لتشتغل محليًا
    for fr in soup.find_all("iframe"):
        if fr.has_attr("sandbox"):
            del fr["sandbox"]

def flatten(url: str) -> str:
    """ارجع HTML قابل للعرض داخل Streamlit components.html."""
    html, final_url = fetch_url(url)
    soup = BeautifulSoup(html, "lxml")

    # تهيئة
    drop_csp_and_noscript(soup)
    absolutize_links(soup, final_url)
    inline_css_js(soup, final_url)
    unsandbox_iframes(soup)

    # أضف سكبربت بسيط لسكروول سلس (اختياري)
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

    return str(soup)

# ==== UI ====
st.title("Streamlit Page Mirror")

default_url = st.query_params.get("url", [""])[0] if isinstance(st.query_params.get("url"), list) else st.query_params.get("url")
url = st.text_input("ضع رابط الصفحة الأصلية (URL):", value=default_url or "", placeholder="https://example.com/page")

col1, col2 = st.columns(2)
with col1:
    btn_iframe = st.button("🔗 جرّب العرض المباشر (iframe)")
with col2:
    btn_flatten = st.button("🧰 عمل نسخة Flatten (مضمّنة)")

st.caption("نصيحة: ابدأ بـ iframe. لو الموقع يمنع التضمين، استخدم Flatten.")

if url and btn_iframe:
    # لو الموقع يسمح بالتضمين — أسهل طريقة
    st.components.v1.iframe(url, height=900, scrolling=True)
elif url and btn_flatten:
    with st.spinner("يجري تجهيز نسخة قابلة للعرض..."):
        try:
            flat_html = flatten(url)
            st.components.v1.html(flat_html, height=900, scrolling=True)
        except Exception as e:
            st.error(f"تعذّر تجهيز الصفحة: {e}")
else:
    st.info("أدخل الرابط ثم اختر إحدى الطريقتين.")

st.markdown("---")
st.write("💡 يمكنك فتح التطبيق مباشرة مع باراميتر:", 
         "`?url=https://example.com/page`")
