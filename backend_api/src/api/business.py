import os
import io
import re
import tempfile
import requests
import datetime
from typing import Tuple, List

from bs4 import BeautifulSoup

from fastapi import UploadFile, HTTPException
from pdfminer.high_level import extract_text as extract_pdf_text
from openpyxl import load_workbook
from docx import Document

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

import httpx

# Optional: Playwright async browser
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Supported AI APIs
AI_MODEL_CLAUDE = "claude-3-opus-20240229"
AI_MODEL_GEMINI = "gemini-pro"

_CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
# Gemini uses `google-generativeai` Python SDK (assumes API key in env GOOGLE_API_KEY)
_GEMINI_MODEL = "gemini-pro"

def _extract_emails(text: str):
    return re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]+", text)

def _extract_phone(text: str):
    phs = re.findall(r"[+]?[\d()\-\s]{8,}", text)
    # filter
    return [ph for ph in phs if len(re.sub(r"\D+", "", ph)) >= 7]

def _guess_employees(text: str):
    # e.g., "500 employees", "450 FTE"
    em = re.findall(r"(\d{2,6})\s+employees?", text, re.I)
    if em:
        return int(em[0])
    return None

def _guess_revenue(text: str):
    # e.g., "$30M", "$500,000"
    m = re.findall(r"\$([\d,.]+[mk]?)", text, re.I)
    if m:
        s = m[0].lower().replace(",","")
        if "m" in s:
            return float(s.replace("m",""))*1e6
        if "k" in s:
            return float(s.replace("k",""))*1e3
        return float(s)
    return None

def _guess_founded(text: str):
    f = re.findall(r"(Founded in|Since)\s+(\d{4})", text, re.I)
    if f:
        return int(f[0][1])
    return None

# PUBLIC_INTERFACE
async def scrape_company_info(url: str) -> Tuple[dict, bool]:
    """
    Scrapes a company website for structured company information.
    Tries requests+BeautifulSoup, falls back to Playwright (JS rendering) if available.

    Returns: (company_dict, found)
    """
    def soup_extract(soup):
        # Extract text and metadata
        text = soup.get_text(" ", strip=True)
        meta = {m.get("name", m.get("property", "")): m.get("content","") for m in soup.find_all("meta")}
        title = soup.title.string.strip() if soup.title else ""
        desc = meta.get("description") or meta.get("og:description") or desc_from_text(text)
        name = meta.get("og:site_name") or meta.get("og:title") or title or ""
        logo_url = meta.get("og:image") or ""
        company = {
            "name": name or "Unknown Company",
            "website": url,
            "industry": meta.get("industry", None),
            "description": desc,
            "headquarters": None,
            "founded_year": _guess_founded(text),
            "email": _extract_emails(text)[0] if _extract_emails(text) else None,
            "phone": _extract_phone(text)[0] if _extract_phone(text) else None,
            "employees": _guess_employees(text),
            "revenue": _guess_revenue(text),
            "logo_url": logo_url,
        }
        # Try HQ address from "Contact", "About" etc.
        for place in soup.find_all(string=re.compile(r"(Address|Headquarters|Location)", re.I)):
            parent = place.find_parent()
            if parent and len(parent.text) < 128:
                company["headquarters"] = parent.text.strip()
                break
        return company

    def desc_from_text(text):
        # First 1-2 sentences ~250 chars that looks like a mission/overview
        parts = re.split(r"[.!?]", text)
        desc = ". ".join(parts[:2]).strip()
        return desc if len(desc) >= 20 else None

    # Try direct requests/BeautifulSoup scrape
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=10, headers=headers)
        if not resp.ok or "text/html" not in resp.headers.get("content-type",""):
            return {}, False
        soup = BeautifulSoup(resp.text, "lxml")
        company = soup_extract(soup)
        found = company["name"] != "Unknown Company" or company["description"] is not None
    except Exception:
        company, found = {}, False

    # If failed, optionally try Playwright (for JS sites)
    if not found and PLAYWRIGHT_AVAILABLE:
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, timeout=15000)
                text = await page.content()
                soup = BeautifulSoup(text, "lxml")
                company = soup_extract(soup)
                await browser.close()
                found = company["name"] != "Unknown Company" or company["description"] is not None
        except Exception:
            return {}, False

    return company, found

# PUBLIC_INTERFACE
async def extract_file_text_and_preview(
    upload_file: UploadFile,
    max_preview_length=400,
) -> Tuple[str, str]:
    """
    Extracts all-generic text from PDF, DOCX, TXT, or XLSX files for content analysis.
    Returns (full_text, preview_text)
    """
    filename = upload_file.filename.lower()
    content = await upload_file.read()

    # PDF
    if filename.endswith(".pdf"):
        tmpf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        try:
            tmpf.write(content)
            tmpf.close()
            text = extract_pdf_text(tmpf.name) or ""
        finally:
            os.unlink(tmpf.name)
    # DOCX
    elif filename.endswith(".docx"):
        try:
            doc = Document(io.BytesIO(content))
            text = "\n".join([p.text for p in doc.paragraphs])
        except Exception:
            text = ""
    # XLSX
    elif filename.endswith(".xlsx"):
        try:
            wb = load_workbook(io.BytesIO(content), data_only=True)
            lines = []
            for ws in wb.worksheets[:2]:
                for row in ws.iter_rows(values_only=True):
                    line = " ".join([str(x or "") for x in row if x])[:80]
                    if line.strip():
                        lines.append(line)
            text = "\n".join(lines)
        except Exception:
            text = ""
    # TXT or other
    elif filename.endswith(".txt"):
        try:
            text = content.decode('utf-8', errors="ignore")
        except Exception:
            text = ""
    else:
        # Attempt generic decode
        try:
            text = content.decode('utf-8', errors="ignore")
        except Exception:
            text = ""
    preview = text.strip().replace("\n", " ")[:max_preview_length]
    return text, preview

# PUBLIC_INTERFACE
async def generate_teaser_with_ai(
    company: dict,
    file_previews: List[str],
    api_choice: str = "claude"
) -> Tuple[str, str]:
    """
    Calls AI APIs (Claude or Gemini) to generate investment teaser content.
    Returns (teaser_title, teaser_body)
    """

    prompt = f"""You are a financial analyst assistant. Given the following company profile and supporting file excerpts, generate a professional investment teaser. Focus on clarity, succinct business summary, financial situation, and US/Europe VC/PE market expectations. Format as Markdown ("## Headline\\nMain text...").

Company Profile:\n{company}
File Excerpts:\n{file_previews}

Output should have a headline and 2-3 paragraphs of teaser content suitable for investor review.
"""

    # Claude API
    if api_choice == "claude":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise HTTPException(500, detail="Claude API key not configured.")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": AI_MODEL_CLAUDE,
            "max_tokens": 600,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }
        async with httpx.AsyncClient(timeout=50) as client:
            resp = await client.post(_CLAUDE_API_URL, headers=headers, json=body)
            if not resp.status_code == 200:
                raise HTTPException(500, detail="Claude API call failed.")
            raw = resp.json()
            parts = raw['content'][0]['text'].split("\n", 1)
            headline = parts[0].strip("# ") if parts else "Teaser"
            body_text = parts[1].strip() if len(parts) > 1 else ""
            return headline, body_text
    # Gemini (Google Generative AI)
    elif api_choice == "gemini":
        try:
            import google.generativeai as genai
        except ImportError:
            raise HTTPException(500, detail="Gemini API - google-generativeai package not installed.")
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise HTTPException(500, detail="Gemini API key not configured.")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(_GEMINI_MODEL)
        result = await model.generate_content_async(prompt, generation_config={"max_output_tokens": 500})
        resp = result.text
        # Try parsing headline/content sections
        parts = resp.split("\n", 1)
        headline = parts[0].replace("#", "").strip() if parts else "Teaser"
        body_text = parts[1].strip() if len(parts) > 1 else ""
        return headline, body_text
    else:
        raise HTTPException(400, detail="Invalid AI model.")

# PUBLIC_INTERFACE
def update_teaser_content_in_db(teaser_obj, title: str, content: str, db_sess):
    """
    Updates teaser record in DB and persists changes.
    """
    teaser_obj.title = title
    teaser_obj.content = content
    db_sess.add(teaser_obj)

# PUBLIC_INTERFACE
def export_teaser_to_pdf(
    title: str,
    content: str,
    company: dict,
    output_path: str,
):
    """
    Generates a basic PDF render of the investment teaser using reportlab.
    """
    c = canvas.Canvas(output_path, pagesize=letter)
    c.setFont('Helvetica-Bold', 15)
    width, height = letter
    margin_y = height - 80
    c.drawString(60, margin_y, title)
    y = margin_y - 30
    c.setFont('Helvetica', 11)
    c.drawString(60, y, f"Company: {company.get('name','')}")
    y -= 18
    c.drawString(60, y, f"Website: {company.get('website','')}")
    y -= 22
    for para in content.split("\n"):
        if not para.strip():
            y -= 12
            continue
        for l in re.findall(r'.{1,88}(?:\s+|$)', para):
            c.drawString(60, y, l.strip())
            y -= 15
            if y < 100:
                c.showPage()
                y = margin_y
    c.setFont('Helvetica-Oblique', 9)
    c.drawString(60,40,f"Teaser generated {datetime.datetime.utcnow().isoformat()[:19]} UTC")
    c.showPage()
    c.save()
