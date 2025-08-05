from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Body
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from uuid import UUID
from typing import List, Optional
import tempfile

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
    Company,
    UploadedFile,
    Teaser,
)
from .database import Base, engine, get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from .business import (
    scrape_company_info,
    extract_file_text_and_preview,
    generate_teaser_with_ai,
    update_teaser_content_in_db,
    export_teaser_to_pdf,
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
    company_dict, found = await scrape_company_info(req.url)
    if not found or not company_dict.get("name"):
        raise HTTPException(status_code=400, detail="Website could not be scraped or no company information found.")
    try:
        company = CompanyInfo(**company_dict)
    except Exception:
        raise HTTPException(status_code=400, detail="Scraping returned malformed data.")
    return ScrapeResponse(company=company, found=True)

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
    company_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Accept file uploads (PDF, DOCX, TXT, XLSX). Parses basic details and returns a list of the uploaded files.
    Attempts meaningful preview/summary of uploaded content.

    Args:
        files (List[UploadFile]): Uploaded files as multipart/form-data.

    Returns:
        UploadResponse: List of all successfully uploaded and recognized files.
    """
    file_infos = []

    for upload_file in files:
        try:
            upload_file.file.seek(0)
            _, preview = await extract_file_text_and_preview(upload_file)
        except Exception:
            preview = None
        upload_file.file.seek(0)
        content = await upload_file.read()
        uploaded_db_file = UploadedFile(
            company_id=company_id,
            filename=upload_file.filename,
            content_type=upload_file.content_type or "application/octet-stream",
            size=len(content),
            preview_text=preview
        )
        db.add(uploaded_db_file)
        file_infos.append(
            UploadedFileInfo(
                filename=upload_file.filename,
                content_type=upload_file.content_type,
                size=len(content),
                preview_text=preview
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
    """
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
    Uses AI models (Claude or Gemini).

    Args:
        req (TeaserGenerationRequest): Session and file selection.

    Returns:
        TeaserGenerationResponse: The generated teaser draft/progress status.
    """
    # Fetch company from session_id
    result = await db.execute(select(Company).where(Company.id == req.session_id))
    company_obj = result.scalar_one_or_none()
    if not company_obj:
        raise HTTPException(status_code=400, detail="Invalid session or company.")

    # Gather latest uploaded file previews associated with company
    file_previews = []
    files_q = await db.execute(select(UploadedFile).where(UploadedFile.company_id == req.session_id))
    files = files_q.scalars().all()
    for f in files:
        # If user selects specific files, use filter
        if req.selected_files and f.filename not in req.selected_files:
            continue
        if f.preview_text:
            file_previews.append(f.preview_text)

    company_dict = {
        "name": company_obj.name,
        "website": company_obj.website,
        "industry": company_obj.industry,
        "description": company_obj.description,
        "headquarters": company_obj.headquarters,
        "founded_year": company_obj.founded_year,
        "email": company_obj.email,
        "phone": company_obj.phone,
        "employees": company_obj.employees,
        "revenue": company_obj.revenue,
        "logo_url": company_obj.logo_url,
    }

    # AI Integration: "claude" by default, else "gemini"
    ai_choice = "claude"
    try:
        title, teaser_text = await generate_teaser_with_ai(company_dict, file_previews, ai_choice=ai_choice)
    except HTTPException as ai_ex:
        raise ai_ex
    except Exception:
        # Soft fallback to generic stub if AI fails
        title = f"Investment Teaser for {company_obj.name}"
        teaser_text = f"Introducing {company_obj.name}! {company_obj.description or 'A dynamic company.'}"

    # Insert/replace teaser record for this company/session
    teaser_obj = Teaser(
        company_id=company_obj.id,
        title=title,
        content=teaser_text,
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

    teaser = TeaserContent(
        teaser_id=teaser_obj.id,
        title=teaser_obj.title,
        content=teaser_obj.content,
        company=company_data,
        generated_at=str(teaser_obj.generated_at),
    )
    return TeaserGenerationResponse(teaser=teaser, status="success")


# PUBLIC_INTERFACE
@app.post(
    "/api/teaser/{teaser_id}/update",
    response_model=TeaserGenerationResponse,
    summary="Edit or update generated teaser content",
    tags=["Teaser"],
    responses={
        200: {"description": "Teaser updated and returned."},
        404: {"description": "Teaser not found."},
        422: {"description": "Validation error."},
    }
)
async def update_teaser(
    teaser_id: UUID,
    updated: TeaserContent = Body(..., description="Updated teaser content and title"),
    db: AsyncSession = Depends(get_db)
):
    """
    Edit or update teaser headline/content on the server (after user preview or manual edit).
    """
    result = await db.execute(select(Teaser).where(Teaser.id == teaser_id))
    teaser_obj = result.scalar_one_or_none()
    if not teaser_obj:
        raise HTTPException(status_code=404, detail="Teaser not found.")

    update_teaser_content_in_db(teaser_obj, updated.title, updated.content, db)
    await db.commit()
    await db.refresh(teaser_obj)

    # Return updated teaser model
    return TeaserGenerationResponse(
        teaser=updated,
        status="success"
    )


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
    result = await db.execute(select(Teaser).where(Teaser.id == teaser_id))
    teaser_obj = result.scalar_one_or_none()
    if not teaser_obj:
        raise HTTPException(status_code=404, detail="Teaser not found.")

    # Export associated company info
    company_obj = teaser_obj.company if teaser_obj.company else None
    company_dict = {
        "name": teaser_obj.company.name if company_obj else "",
        "website": teaser_obj.company.website if company_obj else "",
        "industry": teaser_obj.company.industry if company_obj else "",
        "description": teaser_obj.company.description if company_obj else "",
        "headquarters": teaser_obj.company.headquarters if company_obj else "",
        "founded_year": teaser_obj.company.founded_year if company_obj else None,
        "email": teaser_obj.company.email if company_obj else "",
        "phone": teaser_obj.company.phone if company_obj else "",
        "employees": teaser_obj.company.employees if company_obj else None,
        "revenue": teaser_obj.company.revenue if company_obj else None,
        "logo_url": teaser_obj.company.logo_url if company_obj else "",
    }
    # Generate PDF to a temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmpf:
        export_teaser_to_pdf(
            title=teaser_obj.title,
            content=teaser_obj.content,
            company=company_dict,
            output_path=tmpf.name,
        )
        tmpf.flush()
        tmpf.seek(0)
        pdf_path = tmpf.name

    filename = f"investment_teaser_{teaser_id}.pdf"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=filename,
        headers=headers
    )
