#!/usr/bin/env python3
"""
Weekly auto-update of Kent Irwin's complete publication list.

Pulls works from Kent's public ORCID record, adds any that are new (by DOI or title)
to data/all_pubs.json, and rewrites the block between
<!-- ALL-PUBS-START ... --> and <!-- ALL-PUBS-END --> in publications.html.

Run by .github/workflows/update-publications.yml. Safe to run locally:
    python3 scripts/update_publications.py
"""
import html, json, os, re, sys, urllib.request

ORCID = "0000-0002-2998-9743"
MIN_YEAR = 2025          # only auto-add works from this year on (older ones come from the Stanford list)
SKIP_TYPES = {"conference-abstract", "conference-poster", "lecture-speech", "preprint",
              "working-paper", "other", "data-set", "software"}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "all_pubs.json")
SELECTED = os.path.join(ROOT, "data", "selected_pubs.json")

# A new paper is also added to "Selected Publications" if its title matches one of these
# topics, or if a current group member is an author. Edit these lists as the group changes.
GROUP_TOPICS = ["dmradio", "axion", "hidden photon", "hidden-photon", "dark photon", "upconverter", "rqu",
                "squid", "backaction", "back-action", "squeez", "quantum limit", "quantum sensing",
                "quantum metrology", "lumped-element", "lc resonator", "high-q", "aqfp", "flux trapping",
                "dark matter radio"]
GROUP_MEMBERS = ["Simanovskaia", "Wells", "Keller", "Droster", "Singh", "van Assendelft", "Corbin",
                 "Wright", "Ankel", "Kunder", "Bell", "Marangola"]
PAGE = os.path.join(ROOT, "publications.html")

SHORT = {
    "physical review d": "Phys. Rev. D", "physical review letters": "Phys. Rev. Lett.",
    "physical review research": "Phys. Rev. Research", "physical review applied": "Phys. Rev. Applied",
    "physical review b": "Phys. Rev. B", "physical review a": "Phys. Rev. A",
    "the astrophysical journal": "ApJ", "astrophysical journal": "ApJ",
    "the astrophysical journal letters": "ApJL", "astrophysical journal letters": "ApJL",
    "the astrophysical journal supplement series": "ApJS",
    "journal of cosmology and astroparticle physics": "JCAP",
    "journal of low temperature physics": "J. Low Temp. Phys.",
    "ieee transactions on applied superconductivity": "IEEE Trans. Appl. Supercond.",
    "applied physics letters": "Appl. Phys. Lett.", "journal of applied physics": "J. Appl. Phys.",
    "review of scientific instruments": "Rev. Sci. Instrum.",
    "journal of astronomical telescopes, instruments, and systems": "JATIS",
    "monthly notices of the royal astronomical society": "MNRAS", "nature": "Nature", "science": "Science",
}


def get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "irwin-group-site-updater"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def short_name(full):
    """'Last, First M.' or 'First M. Last' -> 'F. M. Last'."""
    full = full.strip()
    if "," in full:
        last, first = [p.strip() for p in full.split(",", 1)]
    else:
        parts = full.split()
        if len(parts) < 2:
            return full
        last, first = parts[-1], " ".join(parts[:-1])
    inits = " ".join(p[0] + "." for p in re.split(r"[\s\-]+", first) if p and p[0].isalpha())
    return f"{inits} {last}".strip()


def fetch_orcid_works():
    data = get(f"https://pub.orcid.org/v3.0/{ORCID}/works")
    works = []
    for g in data.get("group", []):
        s = (g.get("work-summary") or [None])[0]
        if not s:
            continue
        wtype = (s.get("type") or "").lower()
        if wtype in SKIP_TYPES:
            continue
        title = ((s.get("title") or {}).get("title") or {}).get("value") or ""
        year = (((s.get("publication-date") or {}).get("year") or {}).get("value"))
        journal = ((s.get("journal-title") or {}).get("value")) or ""
        doi = None
        for e in ((s.get("external-ids") or {}).get("external-id") or []):
            if (e.get("external-id-type") or "").lower() == "doi":
                doi = e.get("external-id-value")
                break
        if not title or not year:
            continue
        works.append(dict(title=title.strip(), year=int(year), venue=journal.strip(),
                          doi=doi, put_code=s.get("put-code")))
    return works


def authors_for(put_code):
    try:
        w = get(f"https://pub.orcid.org/v3.0/{ORCID}/work/{put_code}")
    except Exception:
        return ""
    names = []
    for c in ((w.get("contributors") or {}).get("contributor") or []):
        n = ((c.get("credit-name") or {}).get("value")) or ""
        if n:
            names.append(short_name(n))
    if not names:
        return ""
    return ", ".join(names[:3]) + (", et al." if len(names) > 6 else ("" if len(names) <= 3 else ", " + ", ".join(names[3:])))


def li(p):
    t = html.escape(p["title"])
    tl = f'<a href="{p["doi"]}" target="_blank" rel="noopener">{t}</a>' if p.get("doi") else t
    v = html.escape(p["venue"]) if p.get("venue") else ""
    vol = html.escape(p["vol"]) if p.get("vol") else ""
    venue = (f"<em>{v}</em>" + (f", {vol}" if vol else "")) if v else vol
    tag = (f' &nbsp;<a class="tag" href="{p["doi"]}" target="_blank" rel="noopener">'
           f'{html.escape(p.get("tag") or "DOI")}</a>') if p.get("doi") else ""
    return f"""            <li>
              <div class="title">{tl}</div>
              <div class="authors">{html.escape(p.get("authors") or "")}</div>
              <div class="venue">{venue}{tag}</div>
            </li>"""


def is_group_paper(title, authors):
    t = title.lower()
    if any(k in t for k in GROUP_TOPICS):
        return True
    return any(re.search(r"\b" + re.escape(m) + r"\b", authors or "") for m in GROUP_MEMBERS)


def sel_li(p):
    u = p["doi"]
    return f"""          <li>
            <div class="title"><a href="{u}" target="_blank" rel="noopener">{p["title"]}</a></div>
            <div class="authors">{p["authors"]}</div>
            <div class="venue">{p["venue"]} &nbsp;<a class="tag" href="{u}" target="_blank" rel="noopener">{p["tag"]}</a></div>
          </li>"""


def render_selected(sel):
    years = sorted({p["year"] for p in sel}, reverse=True)
    return "".join(f"""        <div class="year-group">
          <h2 class="year-label">{y}</h2>
          <ul class="pubs">
{chr(10).join(sel_li(p) for p in sel if p["year"] == y)}
          </ul>
        </div>
""" for y in years)


def render(pubs):
    years = sorted({p["year"] for p in pubs}, reverse=True)
    return "\n".join(f"""          <div class="year-group ap-year">
            <h2 class="year-label">{y}</h2>
            <ul class="pubs ap-list">
{chr(10).join(li(p) for p in pubs if p["year"] == y)}
            </ul>
          </div>""" for y in years)


def main():
    pubs = json.load(open(DATA))
    sel = json.load(open(SELECTED))
    sel_titles = {norm(re.sub(r"<[^>]+>", "", p["title"]))[:60] for p in sel}
    sel_added = []
    have_doi = {(p.get("doi") or "").lower().split("doi.org/")[-1] for p in pubs if p.get("doi")}
    have_title = {norm(p["title"])[:60] for p in pubs}

    added = []
    for w in fetch_orcid_works():
        if w["year"] < MIN_YEAR:
            continue
        d = (w["doi"] or "").lower()
        if (d and d in have_doi) or norm(w["title"])[:60] in have_title:
            continue
        url = f'https://doi.org/{w["doi"]}' if w["doi"] else None
        venue = w["venue"]
        entry = dict(year=w["year"], title=w["title"], authors=authors_for(w["put_code"]),
                     venue=venue, tag=SHORT.get(venue.lower(), "DOI" if url else None),
                     vol="", doi=url, num=None, source="orcid")
        pubs.append(entry)
        added.append(entry)
        if url and is_group_paper(entry["title"], entry["authors"]) and norm(entry["title"])[:60] not in sel_titles:
            s_entry = dict(year=entry["year"], authors=html.escape(entry["authors"] or "Irwin Group, et al."),
                           title=html.escape(entry["title"]),
                           venue=f"<em>{html.escape(venue)}</em>" if venue else "", doi=url,
                           tag=html.escape(entry["tag"] or "DOI"))
            sel.append(s_entry); sel_added.append(s_entry)
        if d: have_doi.add(d)
        have_title.add(norm(w["title"])[:60])

    if not added:
        print("No new publications.")
        return 0

    pubs.sort(key=lambda p: -p["year"])
    json.dump(pubs, open(DATA, "w"), indent=0)

    page = open(PAGE).read()
    if sel_added:
        sel.sort(key=lambda p: -p["year"])
        json.dump(sel, open(SELECTED, "w"), indent=1, ensure_ascii=False)
        page = re.sub(r"(<!-- SELECTED-PUBS-START.*?-->\n).*?(<!-- SELECTED-PUBS-END -->)",
                      lambda m: m.group(1) + render_selected(sel) + m.group(2), page, flags=re.S)
    page = re.sub(r"(<!-- ALL-PUBS-START.*?-->\n).*?(\n<!-- ALL-PUBS-END -->)",
                  lambda m: m.group(1) + render(pubs) + m.group(2), page, flags=re.S)
    page = re.sub(r"<!--AP-COUNT-->\d+<!--/AP-COUNT-->", f"<!--AP-COUNT-->{len(pubs)}<!--/AP-COUNT-->", page)
    open(PAGE, "w").write(page)
    for a in added:
        print(f'Added: {a["year"]}  {a["title"]}')
    for a in sel_added:
        print(f'  ...also added to Selected Publications: {a["title"]}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
