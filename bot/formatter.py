# ============================================================
#  bot/formatter.py
#  Telegram mesaj formatlayici
# ============================================================

from datetime import datetime


# ── INDIKTOR TURKCE ISIMLERI ─────────────────────────────
IND_TR = {
    "log_log_band":     "Guc Yasasi Bandi",
    "mvrv":             "Piyasa Degeri (MVRV)",
    "nupl":             "Net Kar/Zarar (NUPL)",
    "hash_ribbon":      "Madenci Sagligi",
    "m2":               "Para Arzi (M2)",
    "dxy":              "Dolar Endeksi (DXY)",
    "vix":              "Korku Endeksi (VIX)",
    "fear_greed":       "Korku & Acgozluluk",
    "funding_rate":     "Funding Rate",
    "open_interest":    "Acik Pozisyon",
    "liquidations":     "Likidasyonlar",
    "exchange_flow":    "Borsa Net Akisi",
    "miner_revenue":    "Madenci Geliri",
    "whale_alert":      "Balina Hareketi",
    "weekly_rsi":       "Haftalik RSI",
    "technicals":       "Teknik Analiz",
    "realized_vol":     "Volatilite",
    "coinbase_premium": "Kurumsal Talep",
    "altcoin_dominance":"BTC Dominansi",
}

# ── INDIKTOR YORUM METINLERI ─────────────────────────────
def _interpret(name: str, value: float) -> tuple[str, str]:
    """(ikon, aciklama) donduruyor."""
    n = name.lower().replace("_", "")

    if "loglogband" in n or "loglog" in n:
        if value > 0.5:   return ("checkmark", "Fiyat ucuz bolgede - tarihsel firsat")
        if value > 0.1:   return ("arrow", "Makul seviyede")
        if value < -0.5:  return ("warning", "Pahali bolgeye yaklasiliyor")
        return ("arrow", "Normal bant")

    if "mvrv" in n:
        if value > 0.6:   return ("checkmark", "Deger altinda - guclu al sinyali")
        if value > 0.2:   return ("arrow", "Makul deger")
        if value < -0.4:  return ("warning", "Asiri degerli - dikkat")
        return ("arrow", "Normal")

    if "nupl" in n:
        if value > 0.5:   return ("checkmark", "Yatirimcilar zararda - dip bolge")
        if value < -0.5:  return ("warning", "Asiri kar - tepe riski")
        return ("arrow", "Normal")

    if "hashribbon" in n:
        if value > 0.7:   return ("checkmark", "Madenci teslimiyeti bitti - boga baslangici")
        if value > 0.3:   return ("arrow", "Saglikli hash rate")
        if value < -0.3:  return ("warning", "Madenci baskisi devam ediyor")
        return ("arrow", "Normal")

    if "funding" in n:
        if value > 0.5:   return ("arrow", "Dengeli - bullish")
        if abs(value) < 0.2: return ("arrow", "Notr")
        if value < -0.5:  return ("warning", "Asiri long - tasfiye riski")
        return ("arrow", "Normal")

    if "openinterest" in n:
        if value > 0.6:   return ("checkmark", "Guclu trend - hacim artisiyla destekleniyor")
        if value < -0.3:  return ("warning", "Pozisyon kapaniyor")
        return ("arrow", "Hareketsiz")

    if "liquidation" in n:
        if value > 0.5:   return ("checkmark", "Long tasfiyesi - potansiyel dip")
        if value < -0.5:  return ("warning", "Short tasfiyesi - potansiyel tepe")
        return ("arrow", "Normal seviye")

    if "exchange" in n or "flow" in n:
        if value > 0.4:   return ("checkmark", "Borsadan cikis - hodl sinyali")
        if value < -0.4:  return ("warning", "Borsaya giris - satis baskisi")
        return ("arrow", "Dengeli")

    if "miner" in n:
        if value > 0.5:   return ("checkmark", "Madenci geliri dusuk - kapitulasyon bitti")
        return ("arrow", "Normal")

    if "whale" in n:
        if value > 0.4:   return ("checkmark", "Borsadan cikis - uzun vadeli hodl")
        if value < -0.4:  return ("warning", "Borsaya giris - satis baskisi olusabilir")
        return ("arrow", "Sessiz donem")

    if "weeklyrsi" in n or "rsi" in n:
        if value > 0.5:   return ("checkmark", "Asiri satim bolgesi - toparlanma beklenebilir")
        if value < -0.5:  return ("warning", "Asiri alim bolgesi - duzeltme gelebilir")
        return ("arrow", "Notr")

    if "technical" in n:
        if value > 0.4:   return ("checkmark", "Guclu yukselis momentumu")
        if value < -0.4:  return ("warning", "Dusus momentumu gucleniyor")
        return ("arrow", "Karisik sinyaller")

    if "vol" in n:
        if value > 0.3:   return ("arrow", "Dusuk volatilite - sakin piyasa")
        if value < -0.3:  return ("warning", "Yuksek volatilite - dikkat")
        return ("arrow", "Normal")

    if "coinbase" in n or "premium" in n:
        if value > 0.4:   return ("checkmark", "ABD kurumsal talep artıyor")
        if value < -0.4:  return ("warning", "Kurumsal talep azaliyor")
        return ("arrow", "Normal")

    if "fear" in n or "greed" in n:
        if value > 0.5:   return ("checkmark", "Asiri korku - tarihsel al firsati")
        if value < -0.5:  return ("warning", "Asiri acgozluluk - tepe uyarisi")
        return ("arrow", "Normal ilgi")

    if "dxy" in n:
        if value > 0.3:   return ("checkmark", "Dolar zayifliyor - BTC icin olumlu")
        if value < -0.3:  return ("warning", "Dolar gucleniiyor - risk varliklarini baskılar")
        return ("arrow", "Notr")

    if "vix" in n:
        if value > 0.3:   return ("arrow", "Dusuk korku - sakin piyasa")
        if value < -0.5:  return ("warning", "Panik seviyesi - yuksek volatilite")
        return ("arrow", "Normal")

    if "m2" in n:
        if value > 0.4:   return ("checkmark", "Para arzi genisliyor - likidite artıyor")
        if value < -0.3:  return ("warning", "Para arzi daralıyor - likidite azalıyor")
        return ("arrow", "Normal")

    if "altcoin" in n or "dominan" in n:
        if value > 0.3:   return ("checkmark", "Yuksek BTC dominansi - erken boga")
        if value < -0.3:  return ("warning", "Dusuk dominans - gec boga / altcoin sezonu")
        return ("arrow", "Normal")

    if value > 0.5:   return ("checkmark", "Guclu pozitif sinyal")
    if value < -0.5:  return ("warning", "Guclu negatif sinyal")
    return ("arrow", "Notr")


def _bar(confidence: float, width: int = 8) -> str:
    filled = int(confidence * width)
    filled = max(0, min(width, filled))
    return chr(9608) * filled + chr(9617) * (width - filled)


def _label_with_emoji(label: str) -> str:
    mapping = {
        "GUCLU AL":     "GUCLU AL",
        "TEMKINLI AL":  "TEMKINLI AL",
        "BEKLE":        "BEKLE",
        "DIKKAT":       "DIKKAT",
        "GUCLU KACIN":  "GUCLU KACIN",
    }
    return mapping.get(label, label)


# ── SINYAL MESAJI ─────────────────────────────────────────

def format_signal(result: dict, price: float, timeframe: str) -> str:
    now   = datetime.now().strftime("%d %b - %H:%M")
    score = result["score"]
    label = result["label"]
    conf  = result["confidence"]

    tf_label = {
        "4h": "4 SAATLIK", "1d": "GUNLUK",
        "1w": "HAFTALIK",  "1M": "AYLIK"
    }.get(timeframe, timeframe.upper())

    lines = [
        f"BTC -- {tf_label} SINYAL",
        "=" * 28,
        f"Fiyat       ${price:,.2f}",
        f"Tarih       {now}",
        f"Piyasa      {result['regime_emoji']} {result['regime_label']}",
        "",
        "=" * 28,
        f"*KARAR:     {_label_with_emoji(label)}*",
        f"Skor:       {score:+.3f} / 1.00",
        f"Guven:      %{int(conf * 100)}  {_bar(conf)}",
        "=" * 28,
        "",
    ]

    # Judge bolumu
    judge_v = result.get("judge_verdict", "NORMAL")
    if judge_v != "NORMAL":
        lines.append(f"*Yargi: {result.get('judge_emoji','')} {result.get('judge_label','')}*")
        if result.get("judge_conflict", 0) > 0:
            bull = result.get("judge_bullish", [])
            bear = result.get("judge_bearish", [])
            from core.judge import LAYER_TR
            if bull:
                lines.append(f"  Yukselis: {', '.join(LAYER_TR.get(l, l) for l in bull)}")
            if bear:
                lines.append(f"  Dusus:    {', '.join(LAYER_TR.get(l, l) for l in bear)}")
            lines.append(f"  Guven -%{int(result.get('judge_penalty', 0)*100)} uygulandı")
        lines.append(f"  >> {result.get('judge_hint', '')}")
        lines.append("")

    # Indiktor detaylari
    top5 = result.get("top5", [])
    if top5:
        lines.append("*SINYAL DETAYI:*")
        for i, item in enumerate(top5, 1):
            name  = item["name"]
            tr    = IND_TR.get(name, name)
            val   = item["normalized"]
            stale = item.get("stale", False)

            icon_type, desc = _interpret(name, val)
            if icon_type == "checkmark":
                icon = "[OK]"
            elif icon_type == "warning":
                icon = "[!!]"
            else:
                icon = "[>>]"

            stale_mark = " (eski veri)" if stale else ""
            lines.append(f"{i}. {icon} *{tr}*{stale_mark}")
            lines.append(f"   {desc}")
            lines.append("")

    # Stale/error uyarisi
    stale_c = result.get("stale_count", 0)
    error_c = result.get("error_count", 0)
    if stale_c > 0 or error_c > 0:
        lines.append(f"({stale_c} eski, {error_c} hatali veri)")
        lines.append("")

    # VIX tehlike
    if result.get("vix_danger"):
        lines.append("VIX TEHLIKE BOLGESI -- Riskler artmis durumda")
        lines.append("")

    lines.append("=" * 28)
    lines.append("Yatirim tavsiyesi degildir.")

    return "\n".join(lines)


# ── ANLIK UYARI MESAJI ───────────────────────────────────

def format_alert(result: dict, price: float) -> str:
    score  = result["score"]
    label  = result["label"]
    conf   = result["confidence"]
    is_buy = score > 0
    now    = datetime.now().strftime("%d %b - %H:%M")

    header = "(!!) GUCLU AL SINYALI" if is_buy else "(x) GUCLU KACIN SINYALI"

    lines = [
        f"*{header}*",
        "=" * 28,
        f"BTC -- {now}",
        f"Fiyat:  ${price:,.2f}",
        f"Karar:  {label}",
        f"Skor:   {score:+.3f}",
        f"Guven:  %{int(conf * 100)}",
        f"Piyasa: {result['regime_emoji']} {result['regime_label']}",
        "",
        "*Tetikleyen Sinyaller:*",
    ]

    for item in (result.get("top5") or [])[:3]:
        name  = item["name"]
        tr    = IND_TR.get(name, name)
        val   = item["normalized"]
        _, desc = _interpret(name, val)
        lines.append(f"  [{'+' if val > 0 else '-'}] {tr}")
        lines.append(f"      {desc}")

    lines.append("")
    lines.append("Yatirim tavsiyesi degildir.")
    return "\n".join(lines)


# ── OZET MESAJI ──────────────────────────────────────────

def format_summary(summary: dict) -> str:
    price   = summary["price"]
    results = summary["results"]
    now     = datetime.now().strftime("%H:%M")

    lines = [
        f"*ANLIK OZET -- {now}*",
        "=" * 28,
        f"BTC Fiyat: ${price:,.2f}",
        "",
    ]

    for tf, tf_label in [("4h", "4 Saatlik"), ("1d", "Gunluk"), ("1w", "Haftalik")]:
        r = results.get(tf)
        if not r:
            continue
        bar = _bar(r["confidence"], 6)
        lines.append(f"*{tf_label}:*")
        lines.append(f"  {r['regime_emoji']} {r['regime_label']}")
        lines.append(f"  {r['label']}  ({r['score']:+.2f})")
        lines.append(f"  Guven: %{int(r['confidence']*100)} {bar}")
        if r.get("judge_verdict") not in ("NORMAL", None):
            lines.append(f"  {r['judge_emoji']} {r['judge_label']}")
        lines.append("")

    return "\n".join(lines)


# ── SAGLIK RAPORU ────────────────────────────────────────

def format_health(health: dict) -> str:
    valid  = health.get("valid", [])
    stale  = health.get("stale", [])
    errors = health.get("errors", [])
    total  = health.get("total", 0)

    lines = [
        "*SISTEM SAGLIGI*",
        "=" * 28,
        f"Toplam indiktor: {total}",
        f"Gecerli:  {len(valid)}",
        f"Eski:     {len(stale)}",
        f"Hatali:   {len(errors)}",
        "",
    ]

    if valid:
        v_names = ", ".join(d["name"] for d in valid[:6])
        if len(valid) > 6:
            v_names += f"... (+{len(valid)-6})"
        lines.append(f"*[OK]* {v_names}")

    if stale:
        for d in stale[:3]:
            lines.append(f"*[~]* {d['name']} ({d['age_h']}s once)")

    if errors:
        for d in errors[:3]:
            lines.append(f"*[x]* {d['name']}: {d.get('msg', '')[:40]}")

    return "\n".join(lines)


# ── BASARI RAPORU ────────────────────────────────────────

def format_accuracy(stats: dict) -> str:
    if not stats:
        return "Henuz yeterli sinyal gecmisi yok.\nBot en az 24 saat calismali."

    lines = [
        "*BASARI RAPORU*",
        "=" * 28,
    ]
    for tf, s in stats.items():
        acc = s["accuracy"]
        icon = "[+]" if acc > 60 else "[~]" if acc > 50 else "[-]"
        lines.append(
            f"{icon} {tf}: %{acc} dogru  ({s['correct']}/{s['total']} sinyal)"
        )
        if s.get("avg_pct"):
            lines.append(f"    Ort. hareket: %{s['avg_pct']:+.1f}")

    lines.append("")
    lines.append("Veriler gercek sonuclara gore hesaplanmistir.")
    return "\n".join(lines)


# ── WHALE RAPORU ─────────────────────────────────────────

def format_whale(whale_data: dict) -> str:
    if not whale_data or whale_data.get("normalized", 0) == 0:
        return "Son 24 saatte buyuk BTC transferi tespit edilmedi."

    inn  = whale_data.get("exchange_in_usd", 0)
    out  = whale_data.get("exchange_out_usd", 0)
    net  = whale_data.get("net_flow_usd", 0)
    norm = whale_data.get("normalized", 0)

    direction = "Borsadan CIKIS (hodl)" if norm > 0 else "Borsaya GIRIS (satis baskisi)"

    return "\n".join([
        "*BALINA HAREKETLERİ*",
        "=" * 28,
        f"Son 24 saat:",
        f"  Borsaya giren:  ${inn:.1f}M",
        f"  Borsadan cikan: ${out:.1f}M",
        f"  Net:            ${net:+.1f}M",
        "",
        f"Yorum: {direction}",
    ])


# ── LOG-LOG BAND RAPORU ──────────────────────────────────

def format_band(band_data: dict, price: float) -> str:
    if not band_data or "fair_price" not in band_data:
        return "Log-Log band verisi henuz hazir degil."

    bp  = band_data.get("band_pct", 50)
    verdict = band_data.get("verdict", "NORMAL")

    return "\n".join([
        "*LOG-LOG GUC YASASI BANDI*",
        "=" * 28,
        f"Mevcut Fiyat:  ${price:,.0f}",
        f"Adil Deger:    ${band_data.get('fair_price', 0):,.0f}",
        f"Alt Band:      ${band_data.get('lower_band', 0):,.0f}",
        f"Ust Band:      ${band_data.get('upper_band', 0):,.0f}",
        f"Band Pozisyon: %{bp:.0f}",
        f"Yorum:         {verdict}",
        "",
        "Not: Power Law regresyonuna gore uzun vadeli deger tahmini.",
    ])
