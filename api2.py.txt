from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
import os
from typing import List, Optional

app = FastAPI()

# CORS for your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with your Lovable domain later
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class ResearchQuery(BaseModel):
    question: str

class SavePaperRequest(BaseModel):
    title: str
    authors: str
    abstract: str
    pubmed_id: Optional[str] = None
    doi: Optional[str] = None
    journal: Optional[str] = None
    publication_date: Optional[str] = None

# Your existing search logic
@app.post("/search")
async def search_papers(query: ResearchQuery):
    # Copy your existing Streamlit logic here
    # Return the ranked papers
    pass

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