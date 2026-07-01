# -*- coding: utf-8 -*-
"""
整合版功能：
1. 扫描本地 PDF 文件夹，抽取文本并调用大模型判断是否与微液滴化学相关
2. 无关 PDF 默认移动到 irrelevant_pdfs 文件夹；相关 PDF 则做详细结构化总结
3. 从 CSV / txt / xlsx 读取题目和摘要：
   - 若有 abstract，则严格基于 title + abstract 结构化总结
   - 若无 abstract，则只基于 title 总结
   - 不联网搜索，不依赖外部知识库
4. 合并 PDF 和题目摘要两路结果，做批次总结、总体总结
5. 基于总结自动给出后续可开展方向建议（机器学习 / 聚类 / 智能体）

说明：
- PDF 路线：优先依赖本地 PDF 文本内容
- CSV/题目路线：严格依赖输入文件中的 title / abstract
- 默认不直接删除文件，而是移动到 irrelevant_pdfs，避免误删
"""

import os
import re
import json
import time
import shutil
from pathlib import Path
from typing import List, Dict, Any, Tuple

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


# =====================================
# 1. 基本配置
# =====================================
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise ValueError("未检测到 OPENAI_API_KEY，请先配置环境变量或 .env 文件。")

BASE_URL = os.getenv("OPENAI_BASE_URL", "https://once.novai.su/v1")
MODEL_NAME = os.getenv("OPENAI_MODEL", "gemini-3.1-pro-preview")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# ---------- 输入 ----------
PDF_DIR = r"E:\microdroplet-reference\microdroplet_lit\pdfs"
TITLE_INPUT_FILE = "papers_dedup.csv"   # 支持 txt / csv / xlsx

# ---------- 输出 ----------
OUTPUT_DIR = "microdroplet_analysis_output"
IRRELEVANT_DIR = os.path.join(OUTPUT_DIR, "irrelevant_pdfs")

PDF_RESULTS_XLSX = os.path.join(OUTPUT_DIR, "pdf_results.xlsx")
TITLE_RESULTS_XLSX = os.path.join(OUTPUT_DIR, "title_results.xlsx")
MERGED_RESULTS_XLSX = os.path.join(OUTPUT_DIR, "merged_results.xlsx")

PDF_BATCH_JSON = os.path.join(OUTPUT_DIR, "pdf_batch_summaries.json")
TITLE_BATCH_JSON = os.path.join(OUTPUT_DIR, "title_batch_summaries.json")
MERGED_BATCH_JSON = os.path.join(OUTPUT_DIR, "merged_batch_summaries.json")

OVERALL_SUMMARY_JSON = os.path.join(OUTPUT_DIR, "overall_summary.json")
FUTURE_IDEAS_JSON = os.path.join(OUTPUT_DIR, "future_work_ideas.json")

# ---------- 行为控制 ----------
# keep: 仅标记无关文件，不移动不删除
# move: 移动到 irrelevant_pdfs（推荐）
# delete: 直接删除（不推荐）
HANDLE_IRRELEVANT_MODE = "move"

# ---------- 参数 ----------
REQUEST_INTERVAL = 1.0
BATCH_SIZE = 5

# PDF 文本长度控制
PDF_CLASSIFY_MAX_CHARS = 12000   # 第一阶段：判断是否相关
PDF_DETAIL_MAX_CHARS = 28000     # 第二阶段：相关后做详细抽取


# =====================================
# 2. 通用工具函数
# =====================================
def ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(IRRELEVANT_DIR, exist_ok=True)


def clean_text(text: str) -> str:
    if text is None:
        return ""
    if isinstance(text, float) and pd.isna(text):
        return ""
    text = str(text)
    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_batches(items: List[Any], batch_size: int) -> List[List[Any]]:
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]


def save_json(data: Any, filepath: str):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_excel(data: List[Dict[str, Any]], filepath: str, sheet_name: str = "results"):
    df = pd.DataFrame(data)
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)


def read_csv_robust(csv_path: Path) -> pd.DataFrame:
    """
    尝试多种常见编码读取 CSV，避免中文环境下编码报错。
    """
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb18030", "latin1"]
    last_error = None
    for enc in encodings:
        try:
            return pd.read_csv(csv_path, encoding=enc)
        except Exception as e:
            last_error = e
    raise ValueError(f"CSV 文件读取失败，请检查编码格式。原始错误：{last_error}")


def find_column(df: pd.DataFrame, candidates: List[str]):
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def read_title_abstract_records(input_file: str) -> List[Dict[str, str]]:
    """
    读取题目/摘要输入，支持 txt / csv / xlsx
    返回：
    [
        {"title": "...", "abstract": "..."},
        ...
    ]

    规则：
    1. 如果有摘要列，则读取 title + abstract
    2. 如果没有摘要列，则 abstract 置空，只读 title
    3. 自动兼容常见列名：
       - title / Title / paper_title
       - abstract / Abstract / summary
    """
    path = Path(input_file)
    if not path.exists():
        return []

    suffix = path.suffix.lower()
    records = []

    if suffix == ".txt":
        with open(path, "r", encoding="utf-8") as f:
            titles = [clean_text(x) for x in f.readlines() if clean_text(x)]
        records = [{"title": t, "abstract": ""} for t in titles]

    elif suffix == ".csv":
        df = read_csv_robust(path)

        title_col = find_column(df, ["title", "paper_title", "Title", "TITLE"])
        abstract_col = find_column(df, ["abstract", "summary", "Abstract", "ABSTRACT"])

        if title_col is None:
            raise ValueError("输入文件中未找到 title 列。")

        for _, row in df.iterrows():
            title = clean_text(row.get(title_col, ""))
            abstract = clean_text(row.get(abstract_col, "")) if abstract_col is not None else ""
            if title:
                records.append({
                    "title": title,
                    "abstract": abstract
                })

    elif suffix in [".xlsx", ".xls"]:
        df = pd.read_excel(path)

        title_col = find_column(df, ["title", "paper_title", "Title", "TITLE"])
        abstract_col = find_column(df, ["abstract", "summary", "Abstract", "ABSTRACT"])

        if title_col is None:
            raise ValueError("输入文件中未找到 title 列。")

        for _, row in df.iterrows():
            title = clean_text(row.get(title_col, ""))
            abstract = clean_text(row.get(abstract_col, "")) if abstract_col is not None else ""
            if title:
                records.append({
                    "title": title,
                    "abstract": abstract
                })
    else:
        raise ValueError("TITLE_INPUT_FILE 仅支持 txt / csv / xlsx")

    # 按 title 去重
    seen = set()
    deduped = []
    for r in records:
        key = r["title"]
        if key not in seen:
            deduped.append(r)
            seen.add(key)

    return deduped


# =====================================
# 3. PDF 读取
# =====================================
def list_pdf_files(pdf_dir: str) -> List[str]:
    path = Path(pdf_dir)
    if not path.exists():
        return []
    return [str(p) for p in path.rglob("*.pdf")]


def extract_text_from_pdf(pdf_path: str) -> Tuple[str, str]:
    """
    返回：(title_guess, text)
    """
    if PdfReader is None:
        raise ImportError("未安装 pypdf，请先运行：pip install pypdf")

    try:
        reader = PdfReader(pdf_path)

        title_guess = ""
        try:
            if reader.metadata and reader.metadata.title:
                title_guess = clean_text(reader.metadata.title)
        except Exception:
            pass

        texts = []
        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            page_text = clean_text(page_text)
            if page_text:
                texts.append(page_text)

        full_text = "\n".join(texts)

        if not title_guess:
            first_chunk = full_text[:1500]
            lines = [clean_text(x) for x in re.split(r"[\n\r]+", first_chunk) if clean_text(x)]
            if lines:
                candidate = max(lines[:8], key=len)
                if 10 <= len(candidate) <= 300:
                    title_guess = candidate

        return title_guess, full_text

    except Exception as e:
        print(f"[警告] 读取 PDF 失败: {pdf_path}\n原因: {e}")
        return "", ""


def get_head_tail_text(full_text: str, max_chars: int) -> str:
    """
    兼顾前部和后部内容，避免只截前言。
    """
    full_text = clean_text(full_text)
    if len(full_text) <= max_chars:
        return full_text

    head_ratio = 0.7
    head_len = int(max_chars * head_ratio)
    tail_len = max_chars - head_len
    head = full_text[:head_len]
    tail = full_text[-tail_len:]
    return head + "\n\n[...截断...]\n\n" + tail


# =====================================
# 4. LLM Schema
# =====================================
def get_pdf_classify_schema():
    return {
        "name": "pdf_microdroplet_classification",
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "is_microdroplet_related": {"type": "string"},
                "relevance_level": {"type": "string"},
                "reason": {"type": "string"},
                "delete_or_keep_suggestion": {"type": "string"}
            },
            "required": [
                "title",
                "is_microdroplet_related",
                "relevance_level",
                "reason",
                "delete_or_keep_suggestion"
            ],
            "additionalProperties": False
        }
    }


def get_paper_detail_schema():
    return {
        "name": "microdroplet_paper_detail",
        "schema": {
            "type": "object",
            "properties": {
                "source_type": {"type": "string"},
                "source_name": {"type": "string"},
                "title": {"type": "string"},
                "is_microdroplet_related": {"type": "string"},
                "relevance_level": {"type": "string"},
                "paper_type": {"type": "string"},
                "research_topic": {"type": "string"},
                "reaction_or_process": {"type": "string"},
                "reactants": {"type": "string"},
                "products": {"type": "string"},
                "microdroplet_type": {"type": "string"},
                "droplet_generation_method": {"type": "string"},
                "solvent_or_medium": {"type": "string"},
                "experimental_conditions": {"type": "string"},
                "instrument_or_platform": {"type": "string"},
                "whether_acceleration_discussed": {"type": "string"},
                "acceleration_related_description": {"type": "string"},
                "whether_quantitative_rate_or_yield_info": {"type": "string"},
                "quantitative_information": {"type": "string"},
                "proposed_mechanism": {"type": "string"},
                "whether_theory_computation_involved": {"type": "string"},
                "theory_methods": {"type": "string"},
                "whether_interface_effect_discussed": {"type": "string"},
                "interface_related_factors": {"type": "string"},
                "important_findings": {"type": "string"},
                "key_information_summary": {"type": "string"},
                "uncertainty_note": {"type": "string"}
            },
            "required": [
                "source_type",
                "source_name",
                "title",
                "is_microdroplet_related",
                "relevance_level",
                "paper_type",
                "research_topic",
                "reaction_or_process",
                "reactants",
                "products",
                "microdroplet_type",
                "droplet_generation_method",
                "solvent_or_medium",
                "experimental_conditions",
                "instrument_or_platform",
                "whether_acceleration_discussed",
                "acceleration_related_description",
                "whether_quantitative_rate_or_yield_info",
                "quantitative_information",
                "proposed_mechanism",
                "whether_theory_computation_involved",
                "theory_methods",
                "whether_interface_effect_discussed",
                "interface_related_factors",
                "important_findings",
                "key_information_summary",
                "uncertainty_note"
            ],
            "additionalProperties": False
        }
    }


def get_batch_summary_schema():
    return {
        "name": "microdroplet_batch_summary",
        "schema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "string"},
                "main_topics": {"type": "string"},
                "common_reaction_types": {"type": "string"},
                "common_microdroplet_types": {"type": "string"},
                "common_generation_methods": {"type": "string"},
                "common_solvents_or_media": {"type": "string"},
                "common_experimental_features": {"type": "string"},
                "common_acceleration_features": {"type": "string"},
                "common_interface_factors": {"type": "string"},
                "common_theory_methods": {"type": "string"},
                "important_open_questions": {"type": "string"},
                "batch_summary": {"type": "string"}
            },
            "required": [
                "batch_id",
                "main_topics",
                "common_reaction_types",
                "common_microdroplet_types",
                "common_generation_methods",
                "common_solvents_or_media",
                "common_experimental_features",
                "common_acceleration_features",
                "common_interface_factors",
                "common_theory_methods",
                "important_open_questions",
                "batch_summary"
            ],
            "additionalProperties": False
        }
    }


def get_overall_summary_schema():
    return {
        "name": "microdroplet_overall_summary",
        "schema": {
            "type": "object",
            "properties": {
                "overall_research_focus": {"type": "string"},
                "major_reaction_categories": {"type": "string"},
                "major_microdroplet_categories": {"type": "string"},
                "major_generation_methods": {"type": "string"},
                "common_experimental_conditions": {"type": "string"},
                "common_acceleration_patterns": {"type": "string"},
                "common_interface_mechanisms": {"type": "string"},
                "common_theoretical_computation_features": {"type": "string"},
                "important_scientific_questions": {"type": "string"},
                "research_gaps": {"type": "string"},
                "recommended_next_reading_priorities": {"type": "string"},
                "overall_summary": {"type": "string"}
            },
            "required": [
                "overall_research_focus",
                "major_reaction_categories",
                "major_microdroplet_categories",
                "major_generation_methods",
                "common_experimental_conditions",
                "common_acceleration_patterns",
                "common_interface_mechanisms",
                "common_theoretical_computation_features",
                "important_scientific_questions",
                "research_gaps",
                "recommended_next_reading_priorities",
                "overall_summary"
            ],
            "additionalProperties": False
        }
    }


def get_future_ideas_schema():
    return {
        "name": "future_work_ideas",
        "schema": {
            "type": "object",
            "properties": {
                "machine_learning_directions": {"type": "string"},
                "clustering_and_topic_mining_directions": {"type": "string"},
                "agent_workflow_directions": {"type": "string"},
                "recommended_first_step": {"type": "string"},
                "recommended_data_structure": {"type": "string"},
                "practical_3_month_plan": {"type": "string"}
            },
            "required": [
                "machine_learning_directions",
                "clustering_and_topic_mining_directions",
                "agent_workflow_directions",
                "recommended_first_step",
                "recommended_data_structure",
                "practical_3_month_plan"
            ],
            "additionalProperties": False
        }
    }


# =====================================
# 5. 默认空结果
# =====================================
def empty_paper_result(source_type: str, source_name: str, title: str = "") -> Dict[str, str]:
    return {
        "source_type": source_type,
        "source_name": source_name,
        "title": title or "Unknown",
        "is_microdroplet_related": "Unknown",
        "relevance_level": "Low",
        "paper_type": "Unknown",
        "research_topic": "Unknown",
        "reaction_or_process": "Unknown",
        "reactants": "Unknown",
        "products": "Unknown",
        "microdroplet_type": "Unknown",
        "droplet_generation_method": "Unknown",
        "solvent_or_medium": "Unknown",
        "experimental_conditions": "Unknown",
        "instrument_or_platform": "Unknown",
        "whether_acceleration_discussed": "Unknown",
        "acceleration_related_description": "Unknown",
        "whether_quantitative_rate_or_yield_info": "Unknown",
        "quantitative_information": "Unknown",
        "proposed_mechanism": "Unknown",
        "whether_theory_computation_involved": "Unknown",
        "theory_methods": "Unknown",
        "whether_interface_effect_discussed": "Unknown",
        "interface_related_factors": "Unknown",
        "important_findings": "Unknown",
        "key_information_summary": "Unknown",
        "uncertainty_note": "模型调用失败或信息不足。"
    }


def empty_pdf_classify_result(title_guess: str = ""):
    return {
        "title": title_guess or "Unknown",
        "is_microdroplet_related": "Unknown",
        "relevance_level": "Low",
        "reason": "模型调用失败。",
        "delete_or_keep_suggestion": "keep"
    }


# =====================================
# 6. LLM 调用
# =====================================
def call_json_schema(messages: List[Dict[str, str]], schema: Dict[str, Any], temperature: float = 0.2) -> Dict[str, Any]:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": schema
        },
        temperature=temperature
    )
    content = response.choices[0].message.content
    return json.loads(content)


def classify_pdf_microdroplet(title_guess: str, text_for_classify: str) -> Dict[str, str]:
    schema = get_pdf_classify_schema()
    prompt = f"""
你是一名微液滴化学文献筛选助手。下面给出一篇 PDF 文献的题目猜测和文本内容片段，请判断该文献是否与“微液滴化学 / microdroplet chemistry”相关。

判断标准：
1. 相关主题包括但不限于：
   - microdroplet / droplets / electrospray droplets / charged droplets
   - aerosol droplets / spray droplets
   - droplet-accelerated chemistry
   - air-water interface in droplets
   - water microdroplet reaction / reaction acceleration in droplets
2. 若只是普通液滴流控、微流控、生物液滴、液晶液滴、喷墨打印液滴，而与微液滴化学反应无明显关系，则通常判为 No。
3. 输出字段：
   - is_microdroplet_related: Yes / No / Uncertain
   - relevance_level: High / Medium / Low
   - delete_or_keep_suggestion: keep / remove
4. 只要与微液滴化学关系很弱，就可以建议 remove。
5. 输出必须是 JSON。

题目猜测：
{title_guess}

文本片段：
{text_for_classify}
"""
    try:
        return call_json_schema(
            messages=[
                {"role": "developer", "content": "你是严谨的微液滴化学文献筛选助手。"},
                {"role": "user", "content": prompt}
            ],
            schema=schema,
            temperature=0
        )
    except Exception as e:
        print(f"[警告] PDF 相关性判断失败: {title_guess}\n原因: {e}")
        return empty_pdf_classify_result(title_guess)


def extract_paper_detail_from_pdf(pdf_path: str, title_guess: str, text_for_detail: str) -> Dict[str, str]:
    schema = get_paper_detail_schema()
    filename = os.path.basename(pdf_path)

    prompt = f"""
你是一名微液滴化学文献分析助手。下面给出一篇 PDF 文献的题目猜测和正文片段，请尽可能基于文本内容提取该文献的详细信息。

要求：
1. 输出必须是 JSON。
2. 若信息在文本中未明确出现，则填写 "Unknown"。
3. 输出内容全部用中文，专有名词可保留英文。
4. 重点抽取：
   - 研究主题
   - 反应或过程
   - 反应物与产物
   - 微液滴类型
   - 液滴生成方式
   - 溶剂或介质
   - 实验条件
   - 平台/仪器
   - 是否讨论反应加速
   - 是否有速率/产率等定量信息
   - 是否涉及理论计算
   - 理论方法
   - 是否讨论界面效应
   - 重要发现
5. source_type 固定填写 "pdf"
6. source_name 填写文件名
7. is_microdroplet_related 只能填写 Yes / No / Uncertain
8. relevance_level 只能填写 High / Medium / Low

文件名：
{filename}

题目猜测：
{title_guess}

正文片段：
{text_for_detail}
"""
    try:
        result = call_json_schema(
            messages=[
                {"role": "developer", "content": "你是严谨的微液滴化学文献分析助手。"},
                {"role": "user", "content": prompt}
            ],
            schema=schema,
            temperature=0.1
        )
        result["source_type"] = "pdf"
        result["source_name"] = filename
        if not clean_text(result.get("title", "")):
            result["title"] = title_guess or filename
        return result
    except Exception as e:
        print(f"[警告] PDF 详细抽取失败: {pdf_path}\n原因: {e}")
        return empty_paper_result("pdf", filename, title_guess or filename)


def extract_paper_detail_from_title_abstract(title: str, abstract: str = "") -> Dict[str, str]:
    """
    严格基于输入的题目和摘要抽取，不联网，不补充外部知识。
    """
    schema = get_paper_detail_schema()

    if abstract:
        prompt = f"""
你是一名微液滴化学领域的文献分析助手。现在给你一篇论文的题目和摘要，请严格基于提供的信息进行结构化总结。

要求：
1. 不要联网检索，不要调用外部知识库。
2. 只能依据当前给出的题目和摘要进行判断与总结。
3. 输出必须是 JSON。
4. 若信息未在题目或摘要中明确出现，则填写 "Unknown"。
5. 全部输出用中文，专有名词可保留英文。
6. source_type 固定填写 "title_abstract"
7. source_name 固定填写 "csv_input"
8. is_microdroplet_related 只能填写 Yes / No / Uncertain
9. relevance_level 只能填写 High / Medium / Low
10. 输出重点包括：
   - 研究主题
   - 反应/过程
   - 反应物和产物
   - 微液滴类型
   - 液滴生成方法
   - 溶剂或介质
   - 实验条件
   - 是否讨论反应加速
   - 是否有理论计算
   - 界面因素
   - 重要发现

论文题目：
{title}

论文摘要：
{abstract}
"""
    else:
        prompt = f"""
你是一名微液滴化学领域的文献分析助手。现在只给你一篇论文题目，请严格基于题目本身进行结构化总结。

要求：
1. 不要联网检索，不要调用外部知识库。
2. 只能依据当前给出的题目进行判断。
3. 输出必须是 JSON。
4. 若无法从题目中确定，请填写 "Unknown"。
5. 全部输出用中文，专有名词可保留英文。
6. source_type 固定填写 "title_only"
7. source_name 固定填写 "csv_input"
8. is_microdroplet_related 只能填写 Yes / No / Uncertain
9. relevance_level 只能填写 High / Medium / Low

论文题目：
{title}
"""

    try:
        result = call_json_schema(
            messages=[
                {
                    "role": "developer",
                    "content": "你是严谨的微液滴化学文献分析助手。只能基于用户提供的题目和摘要进行分析，不允许虚构，不允许联网扩展。"
                },
                {"role": "user", "content": prompt}
            ],
            schema=schema,
            temperature=0
        )

        result["source_type"] = "title_abstract" if abstract else "title_only"
        result["source_name"] = "csv_input"

        if not clean_text(result.get("title", "")):
            result["title"] = title

        return result

    except Exception as e:
        print(f"[警告] 题目/摘要抽取失败: {title}\n原因: {e}")
        return empty_paper_result(
            "title_abstract" if abstract else "title_only",
            "csv_input",
            title
        )


def summarize_batch(batch: List[Dict[str, Any]], batch_id: str) -> Dict[str, str]:
    schema = get_batch_summary_schema()
    compact = []
    for x in batch:
        compact.append({
            "source_type": x.get("source_type", "Unknown"),
            "title": x.get("title", "Unknown"),
            "research_topic": x.get("research_topic", "Unknown"),
            "reaction_or_process": x.get("reaction_or_process", "Unknown"),
            "microdroplet_type": x.get("microdroplet_type", "Unknown"),
            "droplet_generation_method": x.get("droplet_generation_method", "Unknown"),
            "solvent_or_medium": x.get("solvent_or_medium", "Unknown"),
            "experimental_conditions": x.get("experimental_conditions", "Unknown"),
            "whether_acceleration_discussed": x.get("whether_acceleration_discussed", "Unknown"),
            "whether_theory_computation_involved": x.get("whether_theory_computation_involved", "Unknown"),
            "theory_methods": x.get("theory_methods", "Unknown"),
            "interface_related_factors": x.get("interface_related_factors", "Unknown"),
            "important_findings": x.get("important_findings", "Unknown")
        })

    prompt = f"""
下面是一批微液滴相关文献的结构化结果，请做批次总结。

要求：
1. 输出 JSON
2. 全部用中文
3. 信息量尽量大一些
4. 总结研究主题、反应类型、微液滴类别、液滴生成方式、常见实验条件、加速规律、界面因素、理论方法、开放问题

批次编号：{batch_id}

输入数据：
{json.dumps(compact, ensure_ascii=False, indent=2)}
"""
    try:
        return call_json_schema(
            messages=[
                {"role": "developer", "content": "你是严谨的微液滴化学综述助手。"},
                {"role": "user", "content": prompt}
            ],
            schema=schema,
            temperature=0.2
        )
    except Exception as e:
        print(f"[警告] 批次总结失败: {batch_id}\n原因: {e}")
        return {
            "batch_id": batch_id,
            "main_topics": "Unknown",
            "common_reaction_types": "Unknown",
            "common_microdroplet_types": "Unknown",
            "common_generation_methods": "Unknown",
            "common_solvents_or_media": "Unknown",
            "common_experimental_features": "Unknown",
            "common_acceleration_features": "Unknown",
            "common_interface_factors": "Unknown",
            "common_theory_methods": "Unknown",
            "important_open_questions": "Unknown",
            "batch_summary": "批次总结失败。"
        }


def overall_summary(all_results: List[Dict[str, Any]], batch_summaries: List[Dict[str, Any]]) -> Dict[str, str]:
    schema = get_overall_summary_schema()
    brief = []
    for x in all_results[:150]:
        brief.append({
            "source_type": x.get("source_type", "Unknown"),
            "title": x.get("title", "Unknown"),
            "research_topic": x.get("research_topic", "Unknown"),
            "reaction_or_process": x.get("reaction_or_process", "Unknown"),
            "microdroplet_type": x.get("microdroplet_type", "Unknown"),
            "droplet_generation_method": x.get("droplet_generation_method", "Unknown"),
            "experimental_conditions": x.get("experimental_conditions", "Unknown"),
            "whether_acceleration_discussed": x.get("whether_acceleration_discussed", "Unknown"),
            "whether_theory_computation_involved": x.get("whether_theory_computation_involved", "Unknown"),
            "interface_related_factors": x.get("interface_related_factors", "Unknown")
        })

    prompt = f"""
下面给出所有微液滴相关文献的部分结构化结果，以及批次总结。请做总体总结。

要求：
1. 输出 JSON
2. 全部用中文
3. 强调：
   - 整体研究重点
   - 主要反应类别
   - 主要微液滴类别
   - 主要液滴生成方式
   - 常见实验条件
   - 常见加速模式
   - 常见界面机制
   - 常见理论计算特征
   - 重要科学问题
   - 研究空白
   - 建议优先深读的文献类别

批次总结：
{json.dumps(batch_summaries, ensure_ascii=False, indent=2)}

部分单篇结果：
{json.dumps(brief, ensure_ascii=False, indent=2)}
"""
    try:
        return call_json_schema(
            messages=[
                {"role": "developer", "content": "你是严谨的微液滴化学研究分析助手。"},
                {"role": "user", "content": prompt}
            ],
            schema=schema,
            temperature=0.2
        )
    except Exception as e:
        print(f"[警告] 总体总结失败\n原因: {e}")
        return {
            "overall_research_focus": "Unknown",
            "major_reaction_categories": "Unknown",
            "major_microdroplet_categories": "Unknown",
            "major_generation_methods": "Unknown",
            "common_experimental_conditions": "Unknown",
            "common_acceleration_patterns": "Unknown",
            "common_interface_mechanisms": "Unknown",
            "common_theoretical_computation_features": "Unknown",
            "important_scientific_questions": "Unknown",
            "research_gaps": "Unknown",
            "recommended_next_reading_priorities": "Unknown",
            "overall_summary": "总体总结失败。"
        }


def generate_future_ideas(overall_summary_dict: Dict[str, Any], all_results: List[Dict[str, Any]]) -> Dict[str, str]:
    schema = get_future_ideas_schema()

    brief = []
    for x in all_results[:150]:
        brief.append({
            "title": x.get("title", "Unknown"),
            "reaction_or_process": x.get("reaction_or_process", "Unknown"),
            "microdroplet_type": x.get("microdroplet_type", "Unknown"),
            "droplet_generation_method": x.get("droplet_generation_method", "Unknown"),
            "solvent_or_medium": x.get("solvent_or_medium", "Unknown"),
            "whether_acceleration_discussed": x.get("whether_acceleration_discussed", "Unknown"),
            "quantitative_information": x.get("quantitative_information", "Unknown"),
            "whether_theory_computation_involved": x.get("whether_theory_computation_involved", "Unknown"),
            "interface_related_factors": x.get("interface_related_factors", "Unknown")
        })

    prompt = f"""
下面给出一批微液滴相关文献的总体总结和部分结构化结果。请基于这些信息，给出后续可开展工作的建议，重点围绕：
1. 机器学习
2. 聚类/主题挖掘
3. 智能体/agent 工作流

要求：
1. 输出 JSON
2. 全部用中文
3. 要求建议具体、可落地，不要空泛
4. machine_learning_directions 中重点说明：
   - 可预测什么
   - 需要哪些特征
   - 什么问题适合监督学习
5. clustering_and_topic_mining_directions 中重点说明：
   - 如何做无监督聚类
   - 能得到什么类型的研究图谱
6. agent_workflow_directions 中重点说明：
   - 智能体可以代替人工完成哪些步骤
   - 一个最实际的 agent 工作流长什么样
7. 给出推荐第一步和 3 个月计划

总体总结：
{json.dumps(overall_summary_dict, ensure_ascii=False, indent=2)}

部分结构化结果：
{json.dumps(brief, ensure_ascii=False, indent=2)}
"""
    try:
        return call_json_schema(
            messages=[
                {"role": "developer", "content": "你是微液滴化学与科研工作流设计助手。"},
                {"role": "user", "content": prompt}
            ],
            schema=schema,
            temperature=0.3
        )
    except Exception as e:
        print(f"[警告] 未来建议生成失败\n原因: {e}")
        return {
            "machine_learning_directions": "Unknown",
            "clustering_and_topic_mining_directions": "Unknown",
            "agent_workflow_directions": "Unknown",
            "recommended_first_step": "Unknown",
            "recommended_data_structure": "Unknown",
            "practical_3_month_plan": "Unknown"
        }


# =====================================
# 7. 无关 PDF 处理
# =====================================
def handle_irrelevant_pdf(pdf_path: str, mode: str):
    if mode == "keep":
        return
    elif mode == "move":
        target = os.path.join(IRRELEVANT_DIR, os.path.basename(pdf_path))
        if os.path.exists(target):
            stem = Path(target).stem
            suffix = Path(target).suffix
            parent = str(Path(target).parent)
            idx = 1
            while True:
                new_target = os.path.join(parent, f"{stem}_{idx}{suffix}")
                if not os.path.exists(new_target):
                    target = new_target
                    break
                idx += 1
        shutil.move(pdf_path, target)
    elif mode == "delete":
        os.remove(pdf_path)
    else:
        raise ValueError(f"不支持的 HANDLE_IRRELEVANT_MODE: {mode}")


# =====================================
# 8. PDF 路线
# =====================================
def process_pdfs(pdf_dir: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    pdf_files = list_pdf_files(pdf_dir)
    print(f"检测到 PDF 文件数：{len(pdf_files)}")

    classify_logs = []
    relevant_results = []

    for i, pdf_path in enumerate(pdf_files, start=1):
        print(f"[PDF {i}/{len(pdf_files)}] {os.path.basename(pdf_path)}")

        title_guess, full_text = extract_text_from_pdf(pdf_path)
        if not full_text:
            classify_logs.append({
                "pdf_path": pdf_path,
                "title_guess": title_guess or os.path.basename(pdf_path),
                "is_microdroplet_related": "Unknown",
                "relevance_level": "Low",
                "reason": "PDF 文本提取失败。",
                "action": "keep"
            })
            continue

        text_for_classify = get_head_tail_text(full_text, PDF_CLASSIFY_MAX_CHARS)
        classify_result = classify_pdf_microdroplet(title_guess, text_for_classify)

        is_related = classify_result.get("is_microdroplet_related", "Unknown")
        action = "keep"

        if is_related == "No":
            action = HANDLE_IRRELEVANT_MODE
            try:
                handle_irrelevant_pdf(pdf_path, HANDLE_IRRELEVANT_MODE)
            except Exception as e:
                print(f"[警告] 无关 PDF 处理失败: {pdf_path}\n原因: {e}")
                action = "keep"

        classify_logs.append({
            "pdf_path": pdf_path,
            "title_guess": title_guess or os.path.basename(pdf_path),
            "is_microdroplet_related": is_related,
            "relevance_level": classify_result.get("relevance_level", "Low"),
            "reason": classify_result.get("reason", ""),
            "action": action
        })

        if is_related in ["Yes", "Uncertain"]:
            text_for_detail = get_head_tail_text(full_text, PDF_DETAIL_MAX_CHARS)
            detail = extract_paper_detail_from_pdf(pdf_path, title_guess, text_for_detail)
            relevant_results.append(detail)

        time.sleep(REQUEST_INTERVAL)

    return classify_logs, relevant_results


# =====================================
# 9. 题目/摘要路线
# =====================================
def process_titles(input_file: str) -> List[Dict[str, Any]]:
    records = read_title_abstract_records(input_file)
    print(f"检测到记录数：{len(records)}")

    results = []
    for i, record in enumerate(records, start=1):
        title = record.get("title", "")
        abstract = record.get("abstract", "")

        print(f"[RECORD {i}/{len(records)}] {title}")
        if abstract:
            print("  -> 使用题目 + 摘要")
        else:
            print("  -> 无摘要，仅使用题目")

        result = extract_paper_detail_from_title_abstract(title, abstract)
        result["input_title"] = title
        result["input_abstract"] = abstract

        results.append(result)
        time.sleep(REQUEST_INTERVAL)

    return results


# =====================================
# 10. 汇总流程
# =====================================
def summarize_results(results: List[Dict[str, Any]], prefix: str) -> List[Dict[str, Any]]:
    batches = split_batches(results, BATCH_SIZE)
    summaries = []

    for i, batch in enumerate(batches, start=1):
        batch_id = f"{prefix}_batch_{i}"
        print(f"[批次总结] {batch_id}")
        summaries.append(summarize_batch(batch, batch_id))
        time.sleep(REQUEST_INTERVAL)

    return summaries


# =====================================
# 11. 主程序
# =====================================
def main():
    ensure_dirs()

    # -------- PDF 路线 --------
    pdf_classify_logs, pdf_results = process_pdfs(PDF_DIR)

    save_excel(pdf_classify_logs, os.path.join(OUTPUT_DIR, "pdf_screening_log.xlsx"), sheet_name="pdf_screening")
    save_excel(pdf_results, PDF_RESULTS_XLSX, sheet_name="pdf_results")

    pdf_batch_summaries = summarize_results(pdf_results, "pdf") if pdf_results else []
    save_json(pdf_batch_summaries, PDF_BATCH_JSON)

    # -------- 题目/摘要路线 --------
    title_results = process_titles(TITLE_INPUT_FILE)
    save_excel(title_results, TITLE_RESULTS_XLSX, sheet_name="title_results")

    title_batch_summaries = summarize_results(title_results, "title") if title_results else []
    save_json(title_batch_summaries, TITLE_BATCH_JSON)

    # -------- 合并 --------
    merged_results = pdf_results + title_results
    save_excel(merged_results, MERGED_RESULTS_XLSX, sheet_name="merged_results")

    merged_batch_summaries = summarize_results(merged_results, "merged") if merged_results else []
    save_json(merged_batch_summaries, MERGED_BATCH_JSON)

    # -------- 总体总结 --------
    overall = overall_summary(merged_results, merged_batch_summaries)
    save_json(overall, OVERALL_SUMMARY_JSON)

    # -------- 后续方向建议 --------
    future_ideas = generate_future_ideas(overall, merged_results)
    save_json(future_ideas, FUTURE_IDEAS_JSON)

    print("\n全部完成。输出文件如下：")
    print(f"1. PDF 初筛日志：{os.path.join(OUTPUT_DIR, 'pdf_screening_log.xlsx')}")
    print(f"2. PDF 详细结果：{PDF_RESULTS_XLSX}")
    print(f"3. 题目/摘要详细结果：{TITLE_RESULTS_XLSX}")
    print(f"4. 合并结果：{MERGED_RESULTS_XLSX}")
    print(f"5. PDF 批次总结：{PDF_BATCH_JSON}")
    print(f"6. 题目批次总结：{TITLE_BATCH_JSON}")
    print(f"7. 合并批次总结：{MERGED_BATCH_JSON}")
    print(f"8. 总体总结：{OVERALL_SUMMARY_JSON}")
    print(f"9. 后续研究建议：{FUTURE_IDEAS_JSON}")


if __name__ == "__main__":
    main()