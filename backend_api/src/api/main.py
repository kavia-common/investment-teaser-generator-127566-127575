from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from uuid import UUID
from typing import List, Optional

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
    Company,
    UploadedFile,
    Teaser,
)
from .database import Base, engine, get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

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
async def health_check():
    """Health Check Endpoint -- returns status message."""
    return {"message": "Healthy"}

@app.on_event("startup")
async def on_startup():
    """Create all database tables on startup if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.on_event("shutdown")
async def on_shutdown():
    """Shutdown event placeholder."""
    # SQLAlchemy async engine has no explicit global teardown
    pass

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
async def scrape_company(req: ScrapeRequest):
    """
    Scrape the given company homepage and attempt to extract company details like name,
    industry, description, logo, headquarters, founded year, and contact info.

    Args:
        req (ScrapeRequest): Contains the URL to be scraped.

    Returns:
        ScrapeResponse: Scraping status and extracted company info (if found).
    """
    # TODO: Implement actual scraping logic here.
    # For now, just return stub company with provided website
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
    files: List[UploadFile] = File(..., description="One or more files to upload (PDF, DOCX, TXT, XLSX)."),
    company_id: Optional[UUID] = None,  # Optionally support associating with company
    db: AsyncSession = Depends(get_db)
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

        # Save metadata to DB
        uploaded_file = UploadedFile(
            company_id=company_id,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            size=len(content),
            preview_text=preview_text
        )
        db.add(uploaded_file)
        file_infos.append(
            UploadedFileInfo(
                filename=file.filename,
                content_type=file.content_type,
                size=len(content),
                preview_text=preview_text
            )
        )
    await db.commit()
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
async def confirm_company(
    req: ConfirmCompanyRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Accepts edited/confirmed company profile from the user.
    Begins a teaser generation workflow, returning a session ID.

    Args:
        req (ConfirmCompanyRequest): Validated company info.

    Returns:
        ConfirmCompanyResponse: Contains a session identifier.
    """
    # Persist company to DB
    company_obj = Company(
        name=req.company.name,
        website=req.company.website,
        industry=req.company.industry,
        description=req.company.description,
        headquarters=req.company.headquarters,
        founded_year=req.company.founded_year,
        email=req.company.email,
        phone=req.company.phone,
        employees=req.company.employees,
        revenue=req.company.revenue,
        logo_url=req.company.logo_url,
    )
    db.add(company_obj)
    await db.commit()
    await db.refresh(company_obj)
    # Use database UUID as session_id
    return ConfirmCompanyResponse(session_id=company_obj.id)

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
async def generate_teaser(
    req: TeaserGenerationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Generates an investment teaser draft based on confirmed company info and uploaded files.
    Uses AI models (stub for now).

    Args:
        req (TeaserGenerationRequest): Session and input selection.

    Returns:
        TeaserGenerationResponse: The generated teaser draft/progress status.
    """
    # Find company by session_id (company_id)
    result = await db.execute(select(Company).where(Company.id == req.session_id))
    company_obj = result.scalar_one_or_none()
    if not company_obj:
        raise HTTPException(status_code=400, detail="Invalid session or missing company.")

    # Generate teaser draft (stub AI integration for now)
    title = f"Investment Teaser for {company_obj.name}"
    content = (
        f"Introducing {company_obj.name}! "
        f"{company_obj.description or 'A dynamic company.'}"
    )

    # Insert Teaser record
    teaser_obj = Teaser(
        company_id=company_obj.id,
        title=title,
        content=content,
    )
    db.add(teaser_obj)
    await db.commit()
    await db.refresh(teaser_obj)

    company_data = CompanyInfo(
        name=company_obj.name,
        website=company_obj.website,
        industry=company_obj.industry,
        description=company_obj.description,
        headquarters=company_obj.headquarters,
        founded_year=company_obj.founded_year,
        email=company_obj.email,
        phone=company_obj.phone,
        employees=company_obj.employees,
        revenue=company_obj.revenue,
        logo_url=company_obj.logo_url,
    )

    # Compose API response model
    teaser = TeaserContent(
        teaser_id=teaser_obj.id,
        title=teaser_obj.title,
        content=teaser_obj.content,
        company=company_data,
        generated_at=str(teaser_obj.generated_at),
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
async def export_teaser(
    teaser_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Exports the generated teaser document (PDF or other formats).

    Args:
        teaser_id (UUID): Generated teaser ID for retrieval/export.

    Returns:
        FileResponse: Downloadable teaser file.
    """
    # Find the teaser in the DB
    result = await db.execute(select(Teaser).where(Teaser.id == teaser_id))
    teaser_obj = result.scalar_one_or_none()
    if not teaser_obj:
        raise HTTPException(status_code=404, detail="Teaser not found.")

    # For now, send metadata response; PDF generation/export will be handled later
    resp_doc = ExportResponse(
        teaser_id=teaser_id,
        filename=f"investment_teaser_{teaser_id}.pdf",
        export_type="pdf",
        download_url=f"/api/export/{teaser_id}"
    )
    return JSONResponse(status_code=200, content=resp_doc.model_dump())
