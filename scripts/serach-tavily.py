import os
import re
import time
import json
import hashlib
from typing import List, Dict, Optional, Tuple

import requests
import pandas as pd
from tqdm import tqdm


# =========================
# 用户可修改参数
# =========================
EMAIL = "gongkeupc@gmail.com"
OPENALEX_API_KEY = "0CiTrgthbzSgVQKWCAfDGT"
TAVILY_API_KEY = "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"

OUTPUT_DIR = "microdroplet_lit"
PDF_DIR = os.path.join(OUTPUT_DIR, "pdfs")
META_DIR = os.path.join(OUTPUT_DIR, "metadata")
LOG_DIR = os.path.join(OUTPUT_DIR, "logs")

QUERIES = [
    "microdroplet",
    "microdroplet chemistry",
    "droplet chemistry",
    "microdroplet reaction acceleration",
    "water microdroplets",
    "aerosol chemistry",
    "microdroplet reaction",
    "electrospray microdroplets",
    "microdroplet interface reaction",
    "charged microdroplet reaction",
    "microdroplet electric field",
    "air-water interface reaction acceleration",
    "microdroplet pH chemistry",
    "microdroplet radical chemistry",
]

ROWS_PER_QUERY = 100
PDF_TIMEOUT = 60
REQUEST_TIMEOUT = 40

HEADERS = {
    "User-Agent": f"MicrodropletLiteratureCollector/1.0 (mailto:{EMAIL})"
}


# =========================
# 基础工具
# =========================
def ensure_dirs():
    for d in [OUTPUT_DIR, PDF_DIR, META_DIR, LOG_DIR]:
        os.makedirs(d, exist_ok=True)


def sleep_brief(sec: float = 1.0):
    time.sleep(sec)


def safe_filename(text: str, max_len: int = 160) -> str:
    text = re.sub(r'[\\/:*?"<>|]+', "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def normalize_title(title: str) -> str:
    if not title:
        return ""
    t = title.lower().strip()
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def normalize_doi(doi: str) -> str:
    if not doi:
        return ""
    doi = doi.strip().lower()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    doi = doi.replace("doi:", "").strip()
    return doi


def make_paper_id(title: str, doi: str) -> str:
    base = normalize_doi(doi) if doi else normalize_title(title)
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def get_json(url: str, params: Optional[dict] = None, headers: Optional[dict] = None, timeout: int = REQUEST_TIMEOUT):
    r = requests.get(url, params=params, headers=headers or HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def post_json(url: str, payload: dict, headers: Optional[dict] = None, timeout: int = REQUEST_TIMEOUT):
    r = requests.post(url, json=payload, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def head_or_get_content_type(url: str, timeout: int = 20) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    try:
        r = requests.head(url, allow_redirects=True, headers=HEADERS, timeout=timeout)
        return r.headers.get("Content-Type", ""), r.status_code, r.url
    except Exception:
        try:
            r = requests.get(url, stream=True, allow_redirects=True, headers=HEADERS, timeout=timeout)
            return r.headers.get("Content-Type", ""), r.status_code, r.url
        except Exception:
            return None, None, None


def download_file(url: str, out_path: str, timeout: int = PDF_TIMEOUT) -> bool:
    try:
        with requests.get(url, stream=True, headers=HEADERS, timeout=timeout, allow_redirects=True) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        f.write(chunk)
        return os.path.exists(out_path) and os.path.getsize(out_path) > 1024
    except Exception:
        return False


def safe_int(x):
    try:
        return int(x)
    except Exception:
        return 0


def unique_urls(urls: List[str]) -> List[str]:
    uniq = []
    for u in urls:
        u = (u or "").strip()
        if u and u not in uniq:
            uniq.append(u)
    return uniq


# =========================
# OpenAlex：主检索
# =========================
def reconstruct_abstract_from_inverted_index(inv_idx: dict) -> str:
    if not inv_idx:
        return ""
    pos_to_word = {}
    for word, positions in inv_idx.items():
        for p in positions:
            pos_to_word[p] = word
    return " ".join(pos_to_word[i] for i in sorted(pos_to_word))


def search_openalex(query: str, rows: int = 50) -> List[Dict]:
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per-page": rows,
        "mailto": EMAIL,
    }
    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY

    data = get_json(url, params=params)
    results = data.get("results", []) or []

    records = []
    for item in results:
        title = item.get("display_name", "")
        year = item.get("publication_year", "")
        doi = normalize_doi(item.get("doi", ""))

        journal = ""
        host = item.get("primary_location", {}).get("source", {}) or {}
        if host:
            journal = host.get("display_name", "")

        authors = []
        for au in item.get("authorships", []) or []:
            name = au.get("author", {}).get("display_name", "")
            if name:
                authors.append(name)

        abstract = ""
        abstract_inv = item.get("abstract_inverted_index")
        if abstract_inv:
            abstract = reconstruct_abstract_from_inverted_index(abstract_inv)

        openalex_id = item.get("id", "")
        is_oa = item.get("open_access", {}).get("is_oa", False)
        citation_count = item.get("cited_by_count", 0)

        pdf_url_candidate = item.get("content_url", "") or ""
        best_oa = item.get("best_oa_location", {}) or {}
        if not pdf_url_candidate:
            pdf_url_candidate = best_oa.get("pdf_url", "") or best_oa.get("landing_page_url", "")

        records.append({
            "source_db": "openalex",
            "query_term": query,
            "title": title,
            "authors": "; ".join(authors),
            "year": year,
            "journal": journal,
            "doi": doi,
            "abstract": abstract,
            "url": item.get("doi", "") or openalex_id,
            "openalex_id": openalex_id,
            "is_oa": is_oa,
            "citation_count": citation_count,
            "pdf_url_candidate": pdf_url_candidate,
            "landing_page_candidate": best_oa.get("landing_page_url", "") or "",
        })
    return records


def get_openalex_by_doi(doi: str) -> Dict:
    doi = normalize_doi(doi)
    if not doi:
        return {}
    url = f"https://api.openalex.org/works/https://doi.org/{doi}"
    params = {"mailto": EMAIL}
    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY
    try:
        return get_json(url, params=params)
    except Exception:
        return {}


# =========================
# Tavily：网页/PDF 兜底
# =========================
def tavily_headers() -> dict:
    return {
        "Authorization": f"Bearer {TAVILY_API_KEY}",
        "Content-Type": "application/json",
    }


def tavily_search_candidates(title: str, doi: str = "", max_results: int = 5) -> List[str]:
    if not TAVILY_API_KEY:
        return []

    queries = []
    if doi:
        queries.append(f'"{doi}" pdf')
    if title:
        queries.append(f'"{title}" pdf')
        queries.append(f'"{title}" filetype:pdf')
        queries.append(f'"{title}" full text')

    all_urls = []
    for q in queries[:3]:
        payload = {
            "query": q,
            "topic": "general",
            "max_results": max_results,
            "include_raw_content": False,
        }
        try:
            data = post_json("https://api.tavily.com/search", payload, headers=tavily_headers())
            for item in data.get("results", []) or []:
                url = item.get("url", "")
                if url:
                    all_urls.append(url)
        except Exception:
            continue

    return unique_urls(all_urls)


def tavily_extract_url(url: str) -> Dict:
    if not TAVILY_API_KEY or not url:
        return {}
    try:
        payload = {"urls": [url]}
        return post_json("https://api.tavily.com/extract", payload, headers=tavily_headers())
    except Exception:
        return {}


# =========================
# 去重与合并
# =========================
def deduplicate_records(records: List[Dict]) -> pd.DataFrame:
    df = pd.DataFrame(records)
    if df.empty:
        return df

    df["doi_norm"] = df["doi"].fillna("").map(normalize_doi)
    df["title_norm"] = df["title"].fillna("").map(normalize_title)

    def agg_text(series):
        vals = [str(x).strip() for x in series if str(x).strip() and str(x).strip().lower() != "nan"]
        if not vals:
            return ""
        uniq = []
        for v in vals:
            if v not in uniq:
                uniq.append(v)
        return " || ".join(uniq)

    agg_map = {col: agg_text for col in df.columns if col not in ["doi_norm", "title_norm"]}
    agg_map["title"] = lambda s: max([str(x) for x in s if str(x).strip()], key=len, default="")
    agg_map["authors"] = lambda s: max([str(x) for x in s if str(x).strip()], key=len, default="")
    agg_map["abstract"] = lambda s: max([str(x) for x in s if str(x).strip()], key=len, default="")
    agg_map["journal"] = lambda s: max([str(x) for x in s if str(x).strip()], key=len, default="")
    agg_map["year"] = lambda s: next((x for x in s if str(x).strip() not in ["", "nan", "None"]), "")
    agg_map["citation_count"] = lambda s: max([safe_int(x) for x in s], default=0)

    has_doi = df["doi_norm"] != ""
    df_doi = df[has_doi].copy()
    df_no_doi = df[~has_doi].copy()

    if not df_doi.empty:
        df_doi = df_doi.groupby("doi_norm", as_index=False).agg(agg_map)
    if not df_no_doi.empty:
        df_no_doi = df_no_doi.groupby("title_norm", as_index=False).agg(agg_map)

    merged = pd.concat([df_doi, df_no_doi], ignore_index=True, sort=False)

    merged["paper_id"] = merged.apply(lambda r: make_paper_id(r.get("title", ""), r.get("doi", "")), axis=1)
    merged["pdf_found"] = False
    merged["pdf_downloaded"] = False
    merged["pdf_url_final"] = ""
    merged["pdf_local_path"] = ""
    merged["download_note"] = ""

    merged["sort_score"] = (
        merged["doi"].fillna("").map(lambda x: 2 if x else 0)
        + merged["abstract"].fillna("").map(lambda x: 1 if x else 0)
        + merged["is_oa"].fillna("").map(lambda x: 1 if str(x).lower() in ["true", "1", "yes"] else 0)
        + merged["citation_count"].fillna(0).map(lambda x: 1 if safe_int(x) > 0 else 0)
    )
    merged = merged.sort_values(["sort_score", "year"], ascending=[False, False]).reset_index(drop=True)
    merged.drop(columns=["sort_score"], inplace=True, errors="ignore")
    return merged


# =========================
# PDF 候选解析
# =========================
def get_pdf_candidates_from_openalex(row: pd.Series) -> List[str]:
    cands = []

    if row.get("pdf_url_candidate"):
        cands.append(str(row["pdf_url_candidate"]).strip())

    doi = str(row.get("doi", "")).strip()
    if doi:
        item = get_openalex_by_doi(doi)
        if item:
            if item.get("content_url"):
                cands.append(item["content_url"])

            best_oa = item.get("best_oa_location", {}) or {}
            if best_oa.get("pdf_url"):
                cands.append(best_oa["pdf_url"])
            if best_oa.get("landing_page_url"):
                cands.append(best_oa["landing_page_url"])

            for loc in item.get("locations", []) or []:
                if loc.get("pdf_url"):
                    cands.append(loc["pdf_url"])
                if loc.get("landing_page_url"):
                    cands.append(loc["landing_page_url"])

    return unique_urls(cands)


def get_pdf_candidates_from_tavily(row: pd.Series) -> List[str]:
    title = str(row.get("title", "")).strip()
    doi = str(row.get("doi", "")).strip()
    return tavily_search_candidates(title=title, doi=doi, max_results=5)


def resolve_pdf_candidates(row: pd.Series) -> List[str]:
    cands = []
    cands.extend(get_pdf_candidates_from_openalex(row))
    cands.extend(get_pdf_candidates_from_tavily(row))
    return unique_urls(cands)


# =========================
# PDF 下载
# =========================
def try_download_pdf_for_row(row: pd.Series) -> Tuple[bool, str, str, str]:
    candidates = resolve_pdf_candidates(row)

    title = row.get("title", "") or "untitled"
    year = str(row.get("year", "") or "")
    authors = str(row.get("authors", "") or "")
    first_author = "unknown"
    if authors:
        first_author = authors.split(";")[0].strip()[:40] or "unknown"

    base_name = safe_filename(f"{year}_{first_author}_{title}")
    out_path = os.path.join(PDF_DIR, base_name + ".pdf")

    for url in candidates:
        ct, status, final_url = head_or_get_content_type(url)
        ct_lower = (ct or "").lower()
        looks_like_pdf = (
            ("pdf" in ct_lower)
            or (final_url and ".pdf" in final_url.lower())
            or ("pdf" in url.lower())
        )

        if looks_like_pdf:
            ok = download_file(url, out_path)
            if ok:
                return True, final_url or url, out_path, "downloaded"

    if candidates:
        return False, candidates[0], "", "landing_page_or_unresolved"
    return False, "", "", "no_pdf_candidate"


# =========================
# 主流程
# =========================
def main():
    ensure_dirs()
    all_records = []

    print("==> 开始检索")
    for q in QUERIES:
        print(f"\n[Query] {q}")
        try:
            recs = search_openalex(q, rows=ROWS_PER_QUERY)
            all_records.extend(recs)
            print(f"  OpenAlex: {len(recs)} 条")
        except Exception as e:
            print(f"  OpenAlex 失败: {e}")
        sleep_brief(1.0)

    raw_df = pd.DataFrame(all_records)
    raw_csv = os.path.join(META_DIR, "papers_raw.csv")
    raw_df.to_csv(raw_csv, index=False, encoding="utf-8-sig")
    print(f"\n==> 原始记录已保存: {raw_csv}")

    print("==> 开始去重")
    dedup_df = deduplicate_records(all_records)
    dedup_csv = os.path.join(META_DIR, "papers_dedup.csv")
    dedup_df.to_csv(dedup_csv, index=False, encoding="utf-8-sig")
    print(f"==> 去重后记录已保存: {dedup_csv}")
    print(f"==> 去重后共 {len(dedup_df)} 篇")

    print("==> 开始尝试下载 PDF")
    for idx in tqdm(range(len(dedup_df))):
        row = dedup_df.iloc[idx]
        success, final_url, local_path, note = try_download_pdf_for_row(row)

        dedup_df.at[idx, "pdf_found"] = bool(final_url)
        dedup_df.at[idx, "pdf_downloaded"] = success
        dedup_df.at[idx, "pdf_url_final"] = final_url
        dedup_df.at[idx, "pdf_local_path"] = local_path
        dedup_df.at[idx, "download_note"] = note

        sleep_brief(0.5)

    final_csv = os.path.join(META_DIR, "papers_with_pdf.csv")
    dedup_df.to_csv(final_csv, index=False, encoding="utf-8-sig")
    print(f"==> PDF 状态表已保存: {final_csv}")

    summary = {
        "total_deduplicated_papers": int(len(dedup_df)),
        "pdf_candidate_found": int(dedup_df["pdf_found"].sum()),
        "pdf_downloaded": int(dedup_df["pdf_downloaded"].sum()),
        "pdf_not_downloaded": int(len(dedup_df) - dedup_df["pdf_downloaded"].sum()),
    }

    summary_path = os.path.join(LOG_DIR, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n==> 完成")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
# 微液滴检索词：你可以继续扩展
QUERIES = [
    "microdroplet chemistry",
    "microdroplet reaction acceleration",
    "water microdroplets",
    "electrospray microdroplets",
    "microdroplet interface reaction",
    "charged microdroplet reaction",
    "microdroplet electric field",
    "air-water interface reaction acceleration",
    "microdroplet pH chemistry",
    "microdroplet radical chemistry"
]

# 每个来源每个 query 最多抓多少条
ROWS_PER_QUERY = 50

# 下载 PDF 超时
PDF_TIMEOUT = 60

# 请求头
HEADERS = {
    "User-Agent": f"MicrodropletLiteratureCollector/1.0 (mailto:{EMAIL})"
}


# =========================
# 工具函数
# =========================
def ensure_dirs():
    for d in [OUTPUT_DIR, PDF_DIR, META_DIR, LOG_DIR]:
        os.makedirs(d, exist_ok=True)


def sleep_brief(sec: float = 1.0):
    time.sleep(sec)


def safe_filename(text: str, max_len: int = 160) -> str:
    text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def normalize_title(title: str) -> str:
    if not title:
        return ""
    t = title.lower().strip()
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def normalize_doi(doi: str) -> str:
    if not doi:
        return ""
    doi = doi.strip().lower()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    doi = doi.replace("doi:", "").strip()
    return doi


def make_paper_id(title: str, doi: str) -> str:
    base = normalize_doi(doi) if doi else normalize_title(title)
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def get_json(url: str, params: Optional[dict] = None, headers: Optional[dict] = None, timeout: int = 40):
    r = requests.get(url, params=params, headers=headers or HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def head_or_get_content_type(url: str, timeout: int = 20) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """
    返回 (content_type, status_code, final_url)
    """
    try:
        r = requests.head(url, allow_redirects=True, headers=HEADERS, timeout=timeout)
        ct = r.headers.get("Content-Type", "")
        return ct, r.status_code, r.url
    except Exception:
        try:
            r = requests.get(url, stream=True, allow_redirects=True, headers=HEADERS, timeout=timeout)
            ct = r.headers.get("Content-Type", "")
            return ct, r.status_code, r.url
        except Exception:
            return None, None, None


def download_file(url: str, out_path: str, timeout: int = PDF_TIMEOUT) -> bool:
    try:
        with requests.get(url, stream=True, headers=HEADERS, timeout=timeout, allow_redirects=True) as r:
            r.raise_for_status()
            content_type = r.headers.get("Content-Type", "").lower()
            if "pdf" not in content_type and not out_path.lower().endswith(".pdf"):
                # 有些 URL 虽不是 pdf content-type，但仍然返回 pdf；这里只做弱判断，不强退
                pass

            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        f.write(chunk)
        return True
    except Exception:
        return False


# =========================
# Crossref
# =========================
def search_crossref(query: str, rows: int = 50) -> List[Dict]:
    """
    Crossref works 接口检索元数据
    """
    url = "https://api.crossref.org/works"
    params = {
        "query": query,
        "rows": rows,
        "mailto": EMAIL,
    }
    data = get_json(url, params=params)
    items = data.get("message", {}).get("items", [])

    records = []
    for item in items:
        title = item.get("title", [""])
        title = title[0] if title else ""
        authors = []
        for a in item.get("author", []) or []:
            name = " ".join([a.get("given", ""), a.get("family", "")]).strip()
            if name:
                authors.append(name)

        abstract = item.get("abstract", "")
        year = None
        issued = item.get("issued", {}).get("date-parts", [])
        if issued and issued[0]:
            year = issued[0][0]

        container = item.get("container-title", [""])
        journal = container[0] if container else ""

        doi = normalize_doi(item.get("DOI", ""))
        url_item = item.get("URL", "")
        links = item.get("link", []) or []

        records.append({
            "source_db": "crossref",
            "query_term": query,
            "title": title,
            "authors": "; ".join(authors),
            "year": year,
            "journal": journal,
            "doi": doi,
            "abstract": abstract,
            "url": url_item,
            "crossref_links": json.dumps(links, ensure_ascii=False),
            "openalex_id": "",
            "pmid": "",
            "pmcid": "",
            "is_oa": "",
            "pdf_url_candidate": ""
        })
    return records


# =========================
# Europe PMC
# =========================
def search_europe_pmc(query: str, rows: int = 50) -> List[Dict]:
    """
    Europe PMC RESTful API 文献检索
    """
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": query,
        "format": "json",
        "pageSize": rows
    }
    data = get_json(url, params=params)
    results = data.get("resultList", {}).get("result", []) or []

    records = []
    for item in results:
        title = item.get("title", "")
        authors = item.get("authorString", "")
        year = item.get("pubYear", "")
        journal = item.get("journalTitle", "")
        doi = normalize_doi(item.get("doi", ""))
        pmid = item.get("pmid", "")
        pmcid = item.get("pmcid", "")
        abstract = item.get("abstractText", "")
        is_oa = item.get("isOpenAccess", "")
        full_text_url = ""

        # Europe PMC 某些记录可通过 pmcid 构造文章页或获取 FT
        if pmcid:
            full_text_url = f"https://europepmc.org/articles/{pmcid}"

        records.append({
            "source_db": "europe_pmc",
            "query_term": query,
            "title": title,
            "authors": authors,
            "year": year,
            "journal": journal,
            "doi": doi,
            "abstract": abstract,
            "url": full_text_url,
            "crossref_links": "",
            "openalex_id": "",
            "pmid": pmid,
            "pmcid": pmcid,
            "is_oa": is_oa,
            "pdf_url_candidate": ""
        })
    return records


# =========================
# OpenAlex
# =========================
def search_openalex(query: str, rows: int = 50) -> List[Dict]:
    """
    OpenAlex works 搜索
    """
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per-page": rows,
        "mailto": EMAIL
    }
    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY

    data = get_json(url, params=params)
    results = data.get("results", []) or []

    records = []
    for item in results:
        title = item.get("display_name", "")
        year = item.get("publication_year", "")
        doi = normalize_doi(item.get("doi", ""))
        journal = ""
        host = item.get("primary_location", {}).get("source", {})
        if host:
            journal = host.get("display_name", "")

        authors = []
        for au in item.get("authorships", []) or []:
            name = au.get("author", {}).get("display_name", "")
            if name:
                authors.append(name)

        abstract = ""
        # OpenAlex 默认 often 不直接给摘要；可留空或后续补
        openalex_id = item.get("id", "")
        is_oa = item.get("open_access", {}).get("is_oa", "")
        pdf_url_candidate = item.get("content_url", "") or ""

        if not pdf_url_candidate:
            best_oa = item.get("best_oa_location", {}) or {}
            pdf_url_candidate = best_oa.get("pdf_url", "") or best_oa.get("landing_page_url", "")

        records.append({
            "source_db": "openalex",
            "query_term": query,
            "title": title,
            "authors": "; ".join(authors),
            "year": year,
            "journal": journal,
            "doi": doi,
            "abstract": abstract,
            "url": item.get("doi", "") or openalex_id,
            "crossref_links": "",
            "openalex_id": openalex_id,
            "pmid": "",
            "pmcid": "",
            "is_oa": is_oa,
            "pdf_url_candidate": pdf_url_candidate
        })
    return records


# =========================
# 数据合并与去重
# =========================
def deduplicate_records(records: List[Dict]) -> pd.DataFrame:
    df = pd.DataFrame(records)
    if df.empty:
        return df

    df["doi_norm"] = df["doi"].fillna("").map(normalize_doi)
    df["title_norm"] = df["title"].fillna("").map(normalize_title)

    # 先按 doi 合并；doi 为空的再按 title 合并
    has_doi = df["doi_norm"] != ""
    df_doi = df[has_doi].copy()
    df_no_doi = df[~has_doi].copy()

    def agg_text(series):
        vals = [str(x).strip() for x in series if str(x).strip() and str(x).strip().lower() != "nan"]
        if not vals:
            return ""
        uniq = []
        for v in vals:
            if v not in uniq:
                uniq.append(v)
        return " || ".join(uniq)

    agg_map = {col: agg_text for col in df.columns if col not in ["doi_norm", "title_norm"]}
    agg_map["year"] = lambda s: next((x for x in s if str(x).strip() not in ["", "nan", "None"]), "")
    agg_map["title"] = lambda s: max([str(x) for x in s if str(x).strip()], key=len, default="")
    agg_map["journal"] = lambda s: max([str(x) for x in s if str(x).strip()], key=len, default="")
    agg_map["authors"] = lambda s: max([str(x) for x in s if str(x).strip()], key=len, default="")
    agg_map["abstract"] = lambda s: max([str(x) for x in s if str(x).strip()], key=len, default="")

    if not df_doi.empty:
        df_doi = df_doi.groupby("doi_norm", as_index=False).agg(agg_map)
    if not df_no_doi.empty:
        df_no_doi = df_no_doi.groupby("title_norm", as_index=False).agg(agg_map)

    merged = pd.concat([df_doi, df_no_doi], ignore_index=True, sort=False)

    merged["paper_id"] = merged.apply(lambda r: make_paper_id(r.get("title", ""), r.get("doi", "")), axis=1)
    merged["pdf_found"] = False
    merged["pdf_downloaded"] = False
    merged["pdf_url_final"] = ""
    merged["pdf_local_path"] = ""
    merged["download_note"] = ""

    # 排序：优先有 doi、有 abstract、有 oa 标记
    merged["sort_score"] = (
        merged["doi"].fillna("").map(lambda x: 1 if x else 0) +
        merged["abstract"].fillna("").map(lambda x: 1 if x else 0) +
        merged["is_oa"].fillna("").map(lambda x: 1 if str(x).lower() in ["y", "yes", "true", "1"] else 0)
    )
    merged = merged.sort_values(["sort_score", "year"], ascending=[False, False]).reset_index(drop=True)
    merged.drop(columns=["sort_score"], inplace=True, errors="ignore")
    return merged


# =========================
# PDF 线索解析
# =========================
def extract_crossref_pdf_candidates(crossref_links_json: str) -> List[str]:
    urls = []
    if not crossref_links_json:
        return urls
    try:
        links = json.loads(crossref_links_json)
        for link in links:
            url = link.get("URL", "")
            ctype = (link.get("content-type", "") or "").lower()
            if url:
                # 优先 pdf，也保留 text-mining 链接作为候选
                if "pdf" in ctype or "application/pdf" in ctype:
                    urls.append(url)
                else:
                    urls.append(url)
    except Exception:
        pass
    return urls


def get_pdf_candidates_from_openalex_by_doi(doi: str) -> List[str]:
    """
    若已有 DOI，再问一次 OpenAlex，尽量找更准确的 OA / pdf_url
    """
    doi = normalize_doi(doi)
    if not doi:
        return []

    url = f"https://api.openalex.org/works/https://doi.org/{doi}"
    params = {"mailto": EMAIL}
    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY

    try:
        item = get_json(url, params=params)
    except Exception:
        return []

    cands = []
    content_url = item.get("content_url", "")
    if content_url:
        cands.append(content_url)

    best_oa = item.get("best_oa_location", {}) or {}
    if best_oa.get("pdf_url"):
        cands.append(best_oa["pdf_url"])
    if best_oa.get("landing_page_url"):
        cands.append(best_oa["landing_page_url"])

    locations = item.get("locations", []) or []
    for loc in locations:
        pdf_url = loc.get("pdf_url", "")
        landing = loc.get("landing_page_url", "")
        if pdf_url:
            cands.append(pdf_url)
        if landing:
            cands.append(landing)

    # 去重
    uniq = []
    for u in cands:
        if u and u not in uniq:
            uniq.append(u)
    return uniq


def get_pdf_candidates_from_europe_pmc(pmcid: str) -> List[str]:
    """
    Europe PMC 若有 PMCID，优先尝试 PMC PDF 链接
    """
    if not pmcid:
        return []

    pmcid = pmcid.strip().upper()
    cands = [
        f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/",
        f"https://europepmc.org/articles/{pmcid}?pdf=render"
    ]
    return cands


def resolve_pdf_candidates(row: pd.Series) -> List[str]:
    cands = []

    # 1) 已有 candidate
    if row.get("pdf_url_candidate"):
        cands.append(str(row.get("pdf_url_candidate")).strip())

    # 2) Crossref links
    cands.extend(extract_crossref_pdf_candidates(str(row.get("crossref_links", ""))))

    # 3) Europe PMC / PMC
    if row.get("pmcid"):
        cands.extend(get_pdf_candidates_from_europe_pmc(str(row.get("pmcid"))))

    # 4) OpenAlex by DOI
    doi = str(row.get("doi", "")).strip()
    if doi:
        cands.extend(get_pdf_candidates_from_openalex_by_doi(doi))

    # 去重
    uniq = []
    for u in cands:
        u = (u or "").strip()
        if u and u not in uniq:
            uniq.append(u)
    return uniq


# =========================
# PDF 下载主逻辑
# =========================
def try_download_pdf_for_row(row: pd.Series) -> Tuple[bool, str, str, str]:
    """
    返回:
    (success, final_pdf_url, local_path, note)
    """
    candidates = resolve_pdf_candidates(row)

    title = row.get("title", "") or "untitled"
    year = str(row.get("year", "") or "")
    first_author = "unknown"
    authors = str(row.get("authors", "") or "")
    if authors:
        first_author = authors.split(";")[0].split(",")[0].strip()[:40] or "unknown"

    base_name = safe_filename(f"{year}_{first_author}_{title}")
    out_path = os.path.join(PDF_DIR, base_name + ".pdf")

    for url in candidates:
        ct, status, final_url = head_or_get_content_type(url)
        ct_lower = (ct or "").lower()

        # 只要看起来像 pdf，就尝试下载
        looks_like_pdf = ("pdf" in ct_lower) or (final_url and ".pdf" in final_url.lower()) or ("pdf" in url.lower())

        if looks_like_pdf:
            ok = download_file(url, out_path)
            if ok and os.path.exists(out_path) and os.path.getsize(out_path) > 1024:
                return True, final_url or url, out_path, "downloaded"

    # 退一步：如果候选只有 landing page，标记出来供手工补
    if candidates:
        return False, candidates[0], "", "landing_page_or_unresolved"

    return False, "", "", "no_pdf_candidate"


# =========================
# 主流程
# =========================
def main():
    ensure_dirs()

    all_records = []

    print("==> 开始检索文献元数据")
    for q in QUERIES:
        print(f"\n[Query] {q}")

        # Crossref
        try:
            recs = search_crossref(q, rows=ROWS_PER_QUERY)
            all_records.extend(recs)
            print(f"  Crossref: {len(recs)} 条")
        except Exception as e:
            print(f"  Crossref 失败: {e}")

        sleep_brief(1.0)

        # Europe PMC
        try:
            recs = search_europe_pmc(q, rows=ROWS_PER_QUERY)
            all_records.extend(recs)
            print(f"  Europe PMC: {len(recs)} 条")
        except Exception as e:
            print(f"  Europe PMC 失败: {e}")

        sleep_brief(1.0)

        # OpenAlex
        try:
            recs = search_openalex(q, rows=ROWS_PER_QUERY)
            all_records.extend(recs)
            print(f"  OpenAlex: {len(recs)} 条")
        except Exception as e:
            print(f"  OpenAlex 失败: {e}")

        sleep_brief(1.0)

    # 保存 raw
    raw_df = pd.DataFrame(all_records)
    raw_csv = os.path.join(META_DIR, "papers_raw.csv")
    raw_df.to_csv(raw_csv, index=False, encoding="utf-8-sig")
    print(f"\n==> 原始记录已保存: {raw_csv}")

    # 去重
    print("==> 开始去重")
    dedup_df = deduplicate_records(all_records)
    dedup_csv = os.path.join(META_DIR, "papers_dedup.csv")
    dedup_df.to_csv(dedup_csv, index=False, encoding="utf-8-sig")
    print(f"==> 去重后记录已保存: {dedup_csv}")
    print(f"==> 去重后共 {len(dedup_df)} 篇")

    # 下载 PDF
    print("==> 开始尝试下载 PDF")
    for idx in tqdm(range(len(dedup_df))):
        row = dedup_df.iloc[idx]
        success, final_url, local_path, note = try_download_pdf_for_row(row)

        dedup_df.at[idx, "pdf_found"] = bool(final_url)
        dedup_df.at[idx, "pdf_downloaded"] = success
        dedup_df.at[idx, "pdf_url_final"] = final_url
        dedup_df.at[idx, "pdf_local_path"] = local_path
        dedup_df.at[idx, "download_note"] = note

        sleep_brief(0.5)

    final_csv = os.path.join(META_DIR, "papers_with_pdf.csv")
    dedup_df.to_csv(final_csv, index=False, encoding="utf-8-sig")
    print(f"==> PDF 状态表已保存: {final_csv}")

    # 输出统计
    total = len(dedup_df)
    found = int(dedup_df["pdf_found"].sum())
    downloaded = int(dedup_df["pdf_downloaded"].sum())

    summary = {
        "total_deduplicated_papers": total,
        "pdf_candidate_found": found,
        "pdf_downloaded": downloaded,
        "pdf_not_downloaded": total - downloaded
    }

    summary_path = os.path.join(LOG_DIR, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n==> 任务完成")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()