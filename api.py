from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
import os
from typing import List, Optional
import asyncio

# Import your research assistant
from research_assistant import ResearchAssistant

app = FastAPI()

# CORS for your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with your Lovable domain later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize research assistant
research_assistant = ResearchAssistant()

class ResearchQuery(BaseModel):
    question: str

class PaperResponse(BaseModel):
    title: str
    authors: List[str]
    abstract: str
    journal: str
    year: str
    pmid: str
    pubmed_url: str
    relevance_score: float
    relevance_reason: str

class SavePaperRequest(BaseModel):
    title: str
    authors: str
    abstract: str
    pubmed_id: Optional[str] = None
    doi: Optional[str] = None
    journal: Optional[str] = None
    publication_date: Optional[str] = None

@app.post("/search", response_model=List[PaperResponse])
async def search_papers(query: ResearchQuery):
    """Search for research papers using the research assistant"""
    try:
        # Use your research assistant to process the question
        papers = await research_assistant.process_research_question(
            question=query.question, 
            max_papers=10
        )
        
        # Convert Paper objects to PaperResponse format
        response_papers = []
        for paper in papers:
            response_papers.append(PaperResponse(
                title=paper.title,
                authors=paper.authors,
                abstract=paper.abstract,
                journal=paper.journal,
                year=paper.year,
                pmid=paper.pmid,
                pubmed_url=paper.pubmed_url,
                relevance_score=paper.relevance_score,
                relevance_reason=paper.relevance_reason
            ))
        
        return response_papers
        
    except Exception as e:
        print(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.post("/papers/save")
async def save_paper(paper: SavePaperRequest, user_token: str):
    # Verify user token with Supabase
    user = supabase.auth.get_user(user_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Save paper to database
    result = supabase.table("saved_papers").insert({
        "user_id": user.user.id,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "pubmed_id": paper.pubmed_id,
        "doi": paper.doi,
        "journal": paper.journal,
        "publication_date": paper.publication_date
    }).execute()
    
    return {"message": "Paper saved successfully"}

@app.get("/papers/saved")
async def get_saved_papers(user_token: str):
    # Get user's saved papers
    user = supabase.auth.get_user(user_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    result = supabase.table("saved_papers").select("*").eq("user_id", user.user.id).execute()
    return result.data

# Health check endpoint
@app.get("/")
async def root():
    return {"message": "Research Assistant API is running"}

# Test endpoint to check if APIs are working
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "anthropic_key": "✓" if os.getenv("ANTHROPIC_API_KEY") else "✗",
        "pubmed_email": "✓" if os.getenv("PUBMED_EMAIL") else "✗"
    }