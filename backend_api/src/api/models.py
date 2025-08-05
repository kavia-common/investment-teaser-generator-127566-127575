from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

from sqlalchemy import Column, String, Integer, Float, Text, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
import uuid

from .database import Base

# SQLAlchemy ORM MODELS

class Company(Base):
    """SQLAlchemy ORM model for company details."""
    __tablename__ = "companies"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    website = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    headquarters = Column(String, nullable=True)
    founded_year = Column(Integer, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    employees = Column(Integer, nullable=True)
    revenue = Column(Float, nullable=True)
    logo_url = Column(String, nullable=True)

    # Relationships
    uploaded_files = relationship("UploadedFile", back_populates="company", cascade="all,delete")
    teasers = relationship("Teaser", back_populates="company", cascade="all,delete")

class UploadedFile(Base):
    """SQLAlchemy ORM model for uploaded files."""
    __tablename__ = "uploaded_files"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(PGUUID(as_uuid=True), ForeignKey("companies.id"))
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    size = Column(Integer, nullable=False)
    preview_text = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    company = relationship("Company", back_populates="uploaded_files")

class Teaser(Base):
    """SQLAlchemy ORM model for generated teasers."""
    __tablename__ = "teasers"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(PGUUID(as_uuid=True), ForeignKey("companies.id"))
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    company = relationship("Company", back_populates="teasers")


# PUBLIC_INTERFACE
class CompanyInfo(BaseModel):
    """Company information model, includes basic identification, description, and financial fields."""
    name: str = Field(..., description="The name of the company.")
    website: Optional[str] = Field(None, description="Official website URL of the company.")
    industry: Optional[str] = Field(None, description="Industry sector (optional, can be detected by scraping).")
    description: Optional[str] = Field(None, description="Short company description/mission.")
    headquarters: Optional[str] = Field(None, description="Location of company headquarters.")
    founded_year: Optional[int] = Field(None, description="Year the company was founded.")
    email: Optional[EmailStr] = Field(None, description="Publicly available contact email address.")
    phone: Optional[str] = Field(None, description="Company's contact phone number.")
    employees: Optional[int] = Field(None, description="Number of employees (if available).")
    revenue: Optional[float] = Field(None, description="Known or estimated company revenue (optional).")
    logo_url: Optional[str] = Field(None, description="URL to the company's logo image.")

# PUBLIC_INTERFACE
class ScrapeRequest(BaseModel):
    """Request body for /api/scrape endpoint; contains the company website URL to be scraped."""
    url: str = Field(..., description="URL of the company's homepage for data extraction.")

# PUBLIC_INTERFACE
class ScrapeResponse(BaseModel):
    """Response for /api/scrape: scraped or extracted initial company info."""
    company: CompanyInfo
    found: bool = Field(..., description="Whether scraping was successful and the company info was found.")

# PUBLIC_INTERFACE
class UploadRequest(BaseModel):
    """Empty model; direct file upload is handled as form-data."""
    pass

# PUBLIC_INTERFACE
class UploadedFileInfo(BaseModel):
    """Describes an uploaded file (e.g. PDF, DOCX, TXT, XLSX) and any parsed content."""
    filename: str = Field(..., description="Name of the uploaded file.")
    content_type: str = Field(..., description="MIME type of the file.")
    size: int = Field(..., description="Size in bytes.")
    preview_text: Optional[str] = Field(None, description="Short text preview (if text extractable).")

# PUBLIC_INTERFACE
class UploadResponse(BaseModel):
    """Response for /api/upload; includes all the uploaded files' properties and parsed previews."""
    files: List[UploadedFileInfo]

# PUBLIC_INTERFACE
class ConfirmCompanyRequest(BaseModel):
    """Request for /api/company/confirm; after user edit/confirmation of company profile."""
    company: CompanyInfo

# PUBLIC_INTERFACE
class ConfirmCompanyResponse(BaseModel):
    """Acknowledgment after confirmation; may include a session identifier."""
    session_id: UUID = Field(..., description="Session identifier for next steps.")

# PUBLIC_INTERFACE
class TeaserGenerationRequest(BaseModel):
    """Data required to generate a teaser."""
    session_id: UUID = Field(..., description="Session identifier linking user progress.")
    selected_files: Optional[List[str]] = Field(None, description="Filenames chosen for teaser generation.")

# PUBLIC_INTERFACE
class TeaserContent(BaseModel):
    """Generated investment teaser content structure."""
    teaser_id: UUID = Field(..., description="Unique teaser identifier for export/viewing.")
    title: str = Field(..., description="Teaser headline.")
    content: str = Field(..., description="Full teaser content (may contain format markers).")
    company: CompanyInfo
    generated_at: str = Field(..., description="Timestamp of teaser generation.")

# PUBLIC_INTERFACE
class TeaserGenerationResponse(BaseModel):
    """Response after teaser draft generation."""
    teaser: TeaserContent
    status: str = Field(..., description="Status of generation (success/pending/error).")

# PUBLIC_INTERFACE
class ExportResponse(BaseModel):
    """When exporting, a direct file response will occur. This model is for OpenAPI docs."""
    teaser_id: UUID
    filename: str
    export_type: str
    download_url: str
