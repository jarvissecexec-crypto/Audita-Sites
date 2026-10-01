"""Detecção de stack tecnológica por assinatura (HTML, headers, cookies, scripts).

Categorias: CMS, e-commerce, framework, analytics, marketing, chat, servidor/CDN,
segurança, fontes, mapas, pagamento, builders.
"""

from __future__ import annotations

import re

# (nome, categoria, [padrões]) — padrões são regex case-insensitive aplicados ao
# HTML + headers + cookies + srcs de script/link concatenados.
SIGNATURES: list[tuple[str, str, list[str]]] = [
    # CMS
    ("WordPress", "cms", [r"/wp-content/", r"/wp-includes/", r'name="generator" content="WordPress']),
    ("Joomla", "cms", [r"/media/jui/", r'name="generator" content="Joomla']),
    ("Drupal", "cms", [r"/sites/all/", r'name="generator" content="Drupal']),
    ("Magento", "cms", [r"/skin/frontend/", r"Mage\.Cookies", r"mage/cookies"]),
    ("PrestaShop", "cms", [r"prestashop", r"presta-"]),
    ("OpenCart", "cms", [r"index\.php\?route=", r"catalog/view/javascript"]),
    ("Shopify", "cms", [r"cdn\.shopify\.com", r"Shopify\.theme", r"shopify"]),
    ("Wix", "cms", [r"wix\.com", r"X-Wix-", r"wixstatic"]),
    ("Squarespace", "cms", [r"squarespace\.com", r"static1\.squarespace"]),
    ("Webflow", "cms", [r"webflow\.(js|com)", r"wf-"]),
    ("HubSpot CMS", "cms", [r"hs-scripts\.com", r"hubspot"]),
    ("Jekyll", "cms", [r"jekyll"]),
    ("Hugo", "cms", [r'hugo', r"gohugo"]),
    ("Contentful", "cms", [r"contentful"]),
    ("Strapi", "cms", [r"strapi"]),
    # Builders / page builders
    ("Elementor", "builder", [r"elementor"]),
    ("WPBakery", "builder", [r"wpbakery", r"vc_row"]),
    ("Divi", "builder", [r"divi", r"et_pb_"]),
    ("Gutenberg", "builder", [r"wp-block-"]),
    # Frameworks / libs
    ("React", "framework", [r"react(\.min|-dom|\.production)", r"__REACT", r"data-reactroot", r"_reactRootContainer"]),
    ("Next.js", "framework", [r"/_next/", r"__NEXT_DATA__", r"__next_f"]),
    ("Nuxt", "framework", [r"/_nuxt/", r"__NUXT__"]),
    ("Vue.js", "framework", [r"vue(\.min|\.runtime|\.js)", r"data-v-[0-9a-f]{8}", r"__VUE"]),
    ("Angular", "framework", [r"ng-version", r"angular(\.min)?\.js", r"ng-app"]),
    ("Svelte", "framework", [r"svelte-\w{5,}"]),
    ("Astro", "framework", [r"astro-island"]),
    ("jQuery", "framework", [r"jquery(\.min)?\.js", r"jQuery\s*=="]),
    ("Bootstrap", "framework", [r"bootstrap(\.min)?\.(css|js)", r"bs5-", r"btn-primary"]),
    ("Tailwind CSS", "framework", [r"tailwind", r"class=\"[^\"]*\b(flex|grid|px-4|text-lg)\b"]),
    ("Bulma", "framework", [r"bulma(\.min)?\.css"]),
    ("Alpine.js", "framework", [r"alpinejs", r"x-data="]),
    ("GSAP", "framework", [r"gsap(\.min)?\.js"]),
    # Analytics
    ("Google Analytics 4", "analytics", [r"gtag\('config',\s?'G-", r"googletagmanager\.com/gtag", r"G-[A-Z0-9]{6,}"]),
    ("Google Analytics (UA)", "analytics", [r"UA-\d{4,}-\d+", r"ga\.js", r"GoogleAnalyticsObject"]),
    ("Google Tag Manager", "analytics", [r"googletagmanager\.com/gtm\.js", r"GTM-[A-Z0-9]+"]),
    ("Meta Pixel", "marketing", [r"facebook\.net/.*fbevents", r"fbq\(", r"connect\.facebook\.net"]),
    ("TikTok Pixel", "marketing", [r"tiktok\.com/i18n/pixel", r"ttq\.", r"analytics\.tiktok\.com"]),
    ("LinkedIn Insight", "marketing", [r"snap\.licdn\.com", r"linkedin\.com/px"]),
    ("Google Ads", "marketing", [r"googleads\.g\.doubleclick", r"google_conversion", r"AW-\d{6,}"]),
    ("RD Station", "marketing", [r"rdstation", r"d335luupugsy2"]),
    ("Hotjar", "analytics", [r"hotjar", r"hjSiteSettings"]),
    ("Clarity", "analytics", [r"clarity\.ms", r"clarity\(/script"]),
    ("Matomo/Piwik", "analytics", [r"matomo", r"piwik"]),
    ("Plausible", "analytics", [r"plausible\.io"]),
    # Chat / atendimento
    ("WhatsApp Button", "chat", [r"api\.whatsapp\.com/send", r"wa\.me/", r"wpp\.connect"]),
    ("Tawk.to", "chat", [r"tawk\.to", r"Tawk_API"]),
    ("Intercom", "chat", [r"intercom", r"widget\.intercom"]),
    ("Zendesk", "chat", [r"zendesk", r"zdassets"]),
    ("Chatwoot", "chat", [r"chatwoot"]),
    ("JivoChat", "chat", [r"jivosite", r"jivo"]),
    ("LiveChat", "chat", [r"livechatinc", r"livechat"]),
    ("ManyChat", "chat", [r"manychat"]),
    # Servidor / CDN / infra
    ("Cloudflare", "infra", [r"cloudflare", r"cf-ray", r"__cf_bm"]),
    ("Nginx", "infra", [r"nginx"]),
    ("Apache", "infra", [r"apache"]),
    ("LiteSpeed", "infra", [r"litespeed", r"LiteSpeed"]),
    ("Vercel", "infra", [r"x-vercel", r"vercel\.app"]),
    ("Netlify", "infra", [r"netlify"]),
    ("AWS", "infra", [r"aws", r"cloudfront", r"x-amz-"]),
    ("Azure", "infra", [r"azure"]),
    ("Google Cloud", "infra", [r"x-goog-", r"googleusercontent"]),
    ("HostGator BR", "infra", [r"hostgator"]),
    ("Locaweb", "infra", [r"locaweb"]),
    ("UOL Host", "infra", [r"uolhost", r"uol\.com\.br"]),
    # Segurança
    ("reCAPTCHA", "seguranca", [r"recaptcha", r"grecaptcha"]),
    ("hCaptcha", "seguranca", [r"hcaptcha"]),
    ("Cloudflare Turnstile", "seguranca", [r"turnstile", r"challenges\.cloudflare"]),
    # Fontes
    ("Google Fonts", "fontes", [r"fonts\.googleapis\.com", r"fonts\.gstatic\.com"]),
    ("Adobe Fonts", "fontes", [r"use\.typekit\.net", r"typekit"]),
    ("Font Awesome", "fontes", [r"font-?awesome", r"fa-\w{2,}"]),
    ("Iconify", "fontes", [r"iconify"]),
    # Mapas / mídia
    ("Google Maps", "mapa", [r"maps\.googleapis|maps\.google\.com/maps", r"google\.com/maps/embed"]),
    ("Leaflet/OSM", "mapa", [r"leaflet", r"openstreetmap"]),
    ("YouTube embed", "midia", [r"youtube\.com/embed", r"youtube-nocookie"]),
    ("Vimeo", "midia", [r"player\.vimeo"]),
    ("Instagram feed", "midia", [r"instagram\.com/embed", r"cdninstagram"]),
    # Pagamento / e-commerce
    ("WooCommerce", "ecommerce", [r"woocommerce", r"wc-"]),
    ("Shopify Checkout", "ecommerce", [r"checkout\.shopify", r"shopify\.com/checkout"]),
    ("Mercado Pago", "ecommerce", [r"mercadopago", r"mercado\.pago"]),
    ("PagSeguro", "ecommerce", [r"pagseguro"]),
    ("Stripe", "ecommerce", [r"js\.stripe\.com", r"stripe\.com/v3"]),
    ("PayPal", "ecommerce", [r"paypal"]),
    ("Carrinho", "ecommerce", [r"/carrinho|/cart|add-to-cart|add_to_cart"]),
    # Formulários / CRM
    ("Typeform", "forms", [r"typeform"]),
    ("Google Forms", "forms", [r"docs\.google\.com/forms"]),
    ("Mailchimp", "forms", [r"mailchimp", r"mc\.validate"]),
    ("MailerLite", "forms", [r"mailerlite"]),
    ("ActiveCampaign", "forms", [r"activecampaign"]),
    ("ConvertKit", "forms", [r"convertkit"]),
]

CATEGORY_LABEL = {
    "cms": "CMS",
    "builder": "Page builder",
    "framework": "Framework / UI",
    "analytics": "Analytics",
    "marketing": "Marketing / Ads",
    "chat": "Atendimento",
    "infra": "Servidor / CDN",
    "seguranca": "Segurança",
    "fontes": "Fontes / Ícones",
    "mapa": "Mapa",
    "midia": "Mídia",
    "ecommerce": "E-commerce / Pagamento",
    "forms": "Formulários / CRM",
}

SECURITY_HEADERS = {
    "strict-transport-security": "HSTS",
    "content-security-policy": "CSP",
    "x-content-type-options": "X-Content-Type-Options",
    "x-frame-options": "X-Frame-Options",
    "referrer-policy": "Referrer-Policy",
    "permissions-policy": "Permissions-Policy",
}


def detect_tech(html: str, headers: dict, cookies: list[dict] | None = None) -> dict:
    """Roda todas as assinaturas contra HTML + headers + cookies."""
    haystack_parts = [html or ""]
    for key, value in (headers or {}).items():
        haystack_parts.append(f"{key}: {value}")
    for cookie in cookies or []:
        haystack_parts.append(str(cookie))
    hay = "\n".join(haystack_parts)

    found: dict[str, list[str]] = {}
    for name, category, patterns in SIGNATURES:
        for pattern in patterns:
            try:
                if re.search(pattern, hay, re.I):
                    found.setdefault(category, []).append(name)
                    break
            except re.error:
                continue

    for cat in found:
        found[cat] = sorted(set(found[cat]))

    server = ""
    for key in ("server", "x-powered-by", "x-served-by"):
        if headers and headers.get(key):
            server = f"{key}: {headers[key]}"
            break

    security = {}
    lowered = {k.lower(): v for k, v in (headers or {}).items()}
    for header, label in SECURITY_HEADERS.items():
        security[label] = bool(lowered.get(header))

    return {
        "by_category": {CATEGORY_LABEL.get(k, k): v for k, v in found.items()},
        "flat": sorted({n for names in found.values() for n in names}),
        "server_header": server,
        "security_headers": security,
        "security_score": int(sum(security.values()) / len(SECURITY_HEADERS) * 100),
    }
