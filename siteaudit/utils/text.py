"""Helpers de texto, URL e normalização (foco em pt-BR)."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urljoin, urlparse

WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9']+")

STOPWORDS_PT = {
    "de", "da", "do", "das", "dos", "e", "em", "para", "por", "com", "sem", "sob",
    "sobre", "entre", "a", "as", "o", "os", "um", "uma", "uns", "umas", "ao", "aos",
    "na", "no", "nas", "nos", "que", "se", "sua", "seu", "suas", "seus", "ele", "ela",
    "você", "voce", "nós", "nos", "mais", "menos", "muito", "como", "quando", "onde",
    "qual", "quais", "todo", "toda", "todos", "todas", "ser", "estar", "ter", "haver",
    "the", "and", "for", "with", "you", "your", "our", "this", "that", "from", "are",
}

PHONE_RE = re.compile(
    r"(?:\+?55[\s\-.]?)?"
    r"(?:\(?\b\d{2}\)?[\s\-.]?)?"
    r"(?:9[\s\-.]?)?\d{4}[\s\-.]?\d{4}\b"
)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

CEP_RE = re.compile(r"\b\d{5}-?\d{3}\b")

WHATSAPP_RE = re.compile(
    r"(?:https?://)?(?:wa\.me|api\.whatsapp\.com/send|web\.whatsapp\.com/send)"
    r"[/?\s]*(?:\?phone=)?([0-9]{10,15})?",
    re.I,
)

SOCIAL_NETS = {
    "instagram": r"instagram\.com/([A-Za-z0-9_\.]{2,40})",
    "facebook": r"facebook\.com/([A-Za-z0-9_\.\-]{2,60})",
    "linkedin": r"linkedin\.com/(?:company|in)/([A-Za-z0-9_\-\.%]{2,80})",
    "youtube": r"youtube\.com/(?:@|c/|channel/|user/)([A-Za-z0-9_\-\.]{2,60})",
    "tiktok": r"tiktok\.com/@([A-Za-z0-9_\.]{2,40})",
    "x": r"(?:twitter|x)\.com/([A-Za-z0-9_]{2,20})",
    "pinterest": r"pinterest\.com/([A-Za-z0-9_]{2,40})",
    "threads": r"threads\.net/@([A-Za-z0-9_\.]{2,40})",
}


def norm_ws(text: str) -> str:
    """Colapsa espaços em branco."""
    return re.sub(r"\s+", " ", (text or "")).strip()


def strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text or "")
        if unicodedata.category(c) != "Mn"
    )


def slugify(text: str, max_len: int = 60) -> str:
    s = strip_accents(text or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:max_len].strip("-") or "site"


def clean_text(html_fragment: str) -> str:
    """Remove tags e normaliza espaços de um fragmento de HTML."""
    import re as _re
    return norm_ws(_re.sub(r"<[^>]+>", " ", html_fragment or ""))


def truncate(text: str, limit: int) -> str:
    text = norm_ws(text)
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


def top_keywords(text: str, limit: int = 15) -> list[tuple[str, int]]:
    """Termos mais frequentes (ignorando stopwords) — útil para entender o posicionamento."""
    tokens = [strip_accents(t.lower()) for t in WORD_RE.findall(text or "")]
    freq: dict[str, int] = {}
    for tok in tokens:
        if len(tok) < 3 or tok.isdigit() or tok in STOPWORDS_PT:
            continue
        freq[tok] = freq.get(tok, 0) + 1
    return sorted(freq.items(), key=lambda kv: -kv[1])[:limit]


def reg_domain(url: str) -> str:
    """Domínio registrável (ex.: loja.com.br)."""
    try:
        import tldextract
        ext = tldextract.extract(url or "")
        return ".".join(p for p in (ext.domain, ext.suffix) if p)
    except Exception:
        host = urlparse(url or "").netloc.lower()
        return host.removeprefix("www.")


def host_of(url: str) -> str:
    return urlparse(url or "").netloc.lower()


def absolutize(url: str, base: str) -> str:
    try:
        return urljoin(base, url)
    except Exception:
        return url


def is_probably_page(url: str) -> bool:
    """Filtra âncoras, tel, mailto e arquivos que não são página HTML."""
    u = (url or "").lower().split("#")[0]
    if not u or u.startswith(("mailto:", "tel:", "javascript:", "data:", "whatsapp:")):
        return False
    return not re.search(r"\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|rar|mp4|mp3|doc|docx|xls|xlsx|css|js|ico|woff2?|ttf)$", u)


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return ""
    if digits.startswith("55") and len(digits) >= 12:
        digits = digits[2:]
    if len(digits) == 10:  # fixo sem 9
        digits = digits[:2] + "9" + digits[2:]
    if len(digits) != 11:
        return ""
    ddd, num = digits[:2], digits[2:]
    return f"({ddd}) {num[:5]}-{num[5:]}"


def extract_phones(text: str, limit: int = 5) -> list[str]:
    out: list[str] = []
    for m in PHONE_RE.finditer(text or ""):
        p = normalize_phone(m.group(0))
        if p and p not in out:
            out.append(p)
        if len(out) >= limit:
            break
    return out


def extract_emails(text: str, limit: int = 5) -> list[str]:
    junk = {"noreply@", "no-reply@", "@example.", "@domain.", "@sentry", "@2x", "@media", "@font-face"}
    out: list[str] = []
    for m in EMAIL_RE.finditer(text or ""):
        e = m.group(0).lower()
        if any(j in e for j in junk) or re.search(r"\.(png|jpg|jpeg|webp|svg|css|js)$", e):
            continue
        if e not in out:
            out.append(e)
        if len(out) >= limit:
            break
    return out


def extract_socials(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for net, pattern in SOCIAL_NETS.items():
        m = re.search(pattern, text or "", re.I)
        if m:
            out[net] = m.group(0) if "http" in m.group(0) else f"{net}.com/" + m.group(1)
            out[net] = out[net] if out[net].startswith("http") else "https://" + out[net]
    return out


def extract_whatsapp(text: str) -> str:
    m = WHATSAPP_RE.search(text or "")
    if not m:
        return ""
    phone = normalize_phone(m.group(1) or "")
    return phone
