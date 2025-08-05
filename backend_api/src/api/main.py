from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from uuid import uuid4, UUID
from typing import List

from .models import (
    ScrapeRequest,
    ScrapeResponse,
    UploadResponse,
    UploadedFileInfo,
    CompanyInfo,
    ConfirmCompanyRequest,
    ConfirmCompanyResponse,
    TeaserGenerationRequest,
    TeaserGenerationResponse,
    TeaserContent,
    ExportResponse,
)

tags_metadata = [
    {"name": "Scraping", "description": "Endpoints for scraping company information"},
    {"name": "Uploading", "description": "File upload and parsing endpoints"},
    {"name": "Company", "description": "Company confirmation and data endpoints"},
    {"name": "Teaser", "description": "Teaser generation and export endpoints"},
]

app = FastAPI(
    title="Investment Teaser Generator API",
    description="FastAPI backend for investment teaser creation. Supports website scraping, file upload, company confirmation, AI-based teaser generation, and PDF export.",
    version="0.1.0",
    openapi_tags=tags_metadata,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", tags=["Misc"])
def health_check():
    """Health Check Endpoint -- returns status message."""
    return {"message": "Healthy"}


# PUBLIC_INTERFACE
@app.post(
    "/api/scrape",
    response_model=ScrapeResponse,
    summary="Scrape company information from website",
    tags=["Scraping"],
    responses={
        200: {"description": "Company info successfully scraped and returned."},
        400: {"description": "Invalid or unreachable URL."},
    }
)
def scrape_company(req: ScrapeRequest):
    """
    Scrape the given company homepage and attempt to extract company details like name,
    industry, description, logo, headquarters, founded year, and contact info.

    Args:
        req (ScrapeRequest): Contains the URL to be scraped.

    Returns:
        ScrapeResponse: Scraping status and extracted company info (if found).
    """
    # Stub implementation for scaffolding
    test_company = CompanyInfo(
        name="Example Corp",
        website=req.url,
        industry="Software",
        description="A sample company for demonstration purposes.",
        headquarters="San Francisco, CA",
        founded_year=2010,
        email="info@example.com",
        phone="555-123-4567",
        employees=42,
        revenue=5000000.0,
        logo_url="https://logo.clearbit.com/example.com"
    )
    return ScrapeResponse(company=test_company, found=True)

# PUBLIC_INTERFACE
@app.post(
    "/api/upload",
    response_model=UploadResponse,
    summary="Upload financial or supporting documents",
    tags=["Uploading"],
    responses={
        200: {"description": "Files uploaded and parsed."},
        400: {"description": "Invalid file upload."},
    }
)
async def upload_files(
    files: List[UploadFile] = File(..., description="One or more files to upload (PDF, DOCX, TXT, XLSX).")
):
    """
    Accept file uploads (PDF, DOCX, TXT, XLSX). Parses basic details and returns a list of the uploaded files.

    Args:
        files (List[UploadFile]): Uploaded files as multipart/form-data.
        
    Returns:
        UploadResponse: List of all successfully uploaded and recognized files.
    """
    file_infos = []
    for file in files:
        content = await file.read(800)
        preview_text = None
        try:
            preview_text = content.decode("utf-8", errors="ignore")[:200]
        except Exception:
            preview_text = None
        file_infos.append(
            UploadedFileInfo(
                filename=file.filename,
                content_type=file.content_type,
                size=len(content),
                preview_text=preview_text
            )
        )
    return UploadResponse(files=file_infos)

# PUBLIC_INTERFACE
@app.post(
    "/api/company/confirm",
    response_model=ConfirmCompanyResponse,
    summary="User confirms or edits company extracted profile",
    tags=["Company"],
    responses={
        200: {"description": "Confirmation accepted, session ID returned."},
        422: {"description": "Validation error."},
    }
)
def confirm_company(req: ConfirmCompanyRequest):
    """
    Accepts edited/confirmed company profile from the user.
    Begins a teaser generation workflow, returning a session ID.

    Args:
        req (ConfirmCompanyRequest): Validated company info.

    Returns:
        ConfirmCompanyResponse: Contains a session identifier.
    """
    session_id = uuid4()
    return ConfirmCompanyResponse(session_id=session_id)

# PUBLIC_INTERFACE
@app.post(
    "/api/generate",
    response_model=TeaserGenerationResponse,
    summary="Trigger AI-based teaser generation",
    tags=["Teaser"],
    responses={
        200: {"description": "Teaser generated.", "model": TeaserGenerationResponse},
        400: {"description": "Invalid session or input."},
    }
)
def generate_teaser(req: TeaserGenerationRequest):
    """
    Generates an investment teaser draft based on confirmed company info and uploaded files.
    Uses AI models (stub for now).

    Args:
        req (TeaserGenerationRequest): Session and input selection.

    Returns:
        TeaserGenerationResponse: The generated teaser draft/progress status.
    """
    # Minimal stub response for scaffolding
    teaser_id = uuid4()
    company_stub = CompanyInfo(
        name="Example Corp",
        website="https://www.example.com"
    )
    teaser = TeaserContent(
        teaser_id=teaser_id,
        title="Sample Investment Teaser",
        content="Introducing Example Corp, an innovative company revolutionizing software.",
        company=company_stub,
        generated_at="2024-07-01T00:00:00Z"
    )
    return TeaserGenerationResponse(teaser=teaser, status="success")

# PUBLIC_INTERFACE
@app.get(
    "/api/export/{teaser_id}",
    summary="Export generated teaser as PDF or other document",
    tags=["Teaser"],
    response_description="Returns teaser as downloadable file.",
    responses={
        200: {"content": {"application/pdf": {}}},
        404: {"description": "Teaser not found."},
    }
)
def export_teaser(teaser_id: UUID):
    """
    Exports the generated teaser document (PDF or other formats).

    Args:
        teaser_id (UUID): Generated teaser ID for retrieval/export.

    Returns:
        FileResponse: Downloadable teaser file.
    """
    # This is a stub: in a real application, file paths and content are dynamic.
    # Return OpenAPI doc annotation:
    resp_doc = ExportResponse(
        teaser_id=teaser_id,
        filename="investment_teaser.pdf",
        export_type="pdf",
        download_url=f"/api/export/{teaser_id}"
    )
    # To comply with OpenAPI, send JSON doc when running in docs mode:
    return JSONResponse(status_code=200, content=resp_doc.model_dump())
