from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
import os
from typing import List, Optional
import asyncio
import time
from collections import defaultdict
from datetime import datetime

# Import your research assistant
from research_assistant import ResearchAssistant

app = FastAPI()

# CORS - Replace with your actual Lovable domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://scholar-search-scribe.lovable.app/",  # TODO: Replace with your actual domain
        "http://localhost:3000",  # For local development
        "https://localhost:3000",  # For local development with HTTPS
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Rate limiting (prevents spam attacks)
rate_limit_store = defaultdict(list)

# Initialize research assistant
research_assistant = ResearchAssistant()

# Data models
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

class UserLimits(BaseModel):
    daily_searches: int
    searches_used_today: int
    can_export: bool
    subscription_tier: str

# Security functions
def get_client_ip(request: Request) -> str:
    """Gets the real IP address of the client (handles proxies)"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host

def check_rate_limit_by_ip(client_ip: str, max_requests: int = 30, window: int = 60) -> bool:
    """
    Prevents spam by limiting requests per IP address
    - max_requests: Maximum requests allowed
    - window: Time window in seconds
    """
    current_time = time.time()
    
    # Remove old requests outside the time window
    rate_limit_store[client_ip] = [
        req_time for req_time in rate_limit_store[client_ip]
        if current_time - req_time < window
    ]
    
    # Check if limit exceeded
    if len(rate_limit_store[client_ip]) >= max_requests:
        return False
    
    # Record this request
    rate_limit_store[client_ip].append(current_time)
    return True

async def verify_user_and_check_limits(authorization: str = Header(None)):
    """
    Verifies the user's login token and checks their subscription limits
    Returns: (user_object, limits_object)
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    token = authorization.split(" ")[1]
    
    try:
        # Verify the user's token with Supabase
        user_response = supabase.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        user = user_response.user
        
        # Get their subscription limits and current usage
        user_limits = await get_user_limits(user.id)
        
        return user, user_limits
        
    except Exception as e:
        print(f"Token verification error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")

async def get_user_limits(user_id: str) -> UserLimits:
    """
    Gets user's subscription tier and calculates their limits
    - Free: 5 searches/day, no export
    - Premium: 50 searches/day, export allowed
    - Pro: 200 searches/day, export allowed
    """
    try:
        # Get user's subscription info
        subscription_result = supabase.table("user_subscriptions").select("*").eq("user_id", user_id).execute()
        
        # Default limits for free users
        daily_searches = 5
        can_export = False
        subscription_tier = "free"
        
        # If user has a subscription record, use those limits
        if subscription_result.data and len(subscription_result.data) > 0:
            sub = subscription_result.data[0]
            subscription_tier = sub.get("tier", "free")
            
            if subscription_tier == "premium":
                daily_searches = 50
                can_export = True
            elif subscription_tier == "pro":
                daily_searches = 200
                can_export = True
        
        # Check how many searches they've used today
        today = datetime.now().date()
        usage_result = supabase.table("user_usage").select("*").eq("user_id", user_id).eq("date", str(today)).execute()
        
        searches_used_today = 0
        if usage_result.data and len(usage_result.data) > 0:
            searches_used_today = usage_result.data[0].get("searches_count", 0)
        
        return UserLimits(
            daily_searches=daily_searches,
            searches_used_today=searches_used_today,
            can_export=can_export,
            subscription_tier=subscription_tier
        )
        
    except Exception as e:
        print(f"Error getting user limits: {e}")
        # Return safe defaults if there's an error
        return UserLimits(
            daily_searches=5,
            searches_used_today=0,
            can_export=False,
            subscription_tier="free"
        )

async def increment_user_usage(user_id: str):
    """
    Adds 1 to the user's daily search count
    Creates a new record if it's their first search today
    """
    try:
        today = datetime.now().date()
        
        # Check if user already has a record for today
        existing = supabase.table("user_usage").select("*").eq("user_id", user_id).eq("date", str(today)).execute()
        
        if existing.data and len(existing.data) > 0:
            # Update existing record
            new_count = existing.data[0]["searches_count"] + 1
            supabase.table("user_usage").update({"searches_count": new_count}).eq("user_id", user_id).eq("date", str(today)).execute()
        else:
            # Create new record for today
            supabase.table("user_usage").insert({
                "user_id": user_id,
                "date": str(today),
                "searches_count": 1
            }).execute()
            
    except Exception as e:
        print(f"Error incrementing usage: {e}")

def validate_research_query(query: ResearchQuery):
    """Validates the search query input"""
    if not query.question or not query.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    if len(query.question) > 500:
        raise HTTPException(status_code=400, detail="Question too long (max 500 characters)")
    
    return query

# API Endpoints
@app.post("/search", response_model=List[PaperResponse])
async def search_papers(
    query: ResearchQuery,
    request: Request,
    user_data = Depends(verify_user_and_check_limits)
):
    """
    Main search endpoint - requires user login
    Checks rate limits, user limits, then searches for papers
    """
    user, limits = user_data
    
    # Check IP-based rate limiting (prevents spam attacks)
    client_ip = get_client_ip(request)
    if not check_rate_limit_by_ip(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again in a minute.")
    
    # Check if user has exceeded their daily search limit
    if limits.searches_used_today >= limits.daily_searches:
        raise HTTPException(
            status_code=403, 
            detail=f"Daily search limit reached ({limits.daily_searches} searches per day). Upgrade your plan for more searches."
        )
    
    # Validate the search query
    query = validate_research_query(query)
    
    try:
        # Actually search for papers using your research assistant
        papers = await research_assistant.process_research_question(
            question=query.question, 
            max_papers=10
        )
        
        # Count this search against their daily limit
        await increment_user_usage(user.id)
        
        # Convert to response format
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
        raise HTTPException(status_code=500, detail="Search failed. Please try again.")

@app.get("/user/limits")
async def get_user_limits_endpoint(user_data = Depends(verify_user_and_check_limits)):
    """
    Returns user's current subscription info and usage
    Frontend can use this to show remaining searches
    """
    user, limits = user_data
    
    return {
        "subscription_tier": limits.subscription_tier,
        "daily_searches": limits.daily_searches,
        "searches_used_today": limits.searches_used_today,
        "searches_remaining": limits.daily_searches - limits.searches_used_today,
        "can_export": limits.can_export
    }

@app.post("/papers/save")
async def save_paper(
    paper: SavePaperRequest,
    user_data = Depends(verify_user_and_check_limits)
):
    """Save a paper to user's collection"""
    user, limits = user_data
    
    try:
        result = supabase.table("saved_papers").insert({
            "user_id": user.id,
            "title": paper.title,
            "authors": paper.authors,
            "abstract": paper.abstract,
            "pubmed_id": paper.pubmed_id,
            "doi": paper.doi,
            "journal": paper.journal,
            "publication_date": paper.publication_date
        }).execute()
        
        return {"message": "Paper saved successfully"}
    
    except Exception as e:
        print(f"Save error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save paper")

@app.get("/papers/saved")
async def get_saved_papers(user_data = Depends(verify_user_and_check_limits)):
    """Get user's saved papers"""
    user, limits = user_data
    
    try:
        result = supabase.table("saved_papers").select("*").eq("user_id", user.id).execute()
        return result.data
    
    except Exception as e:
        print(f"Fetch error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch papers")

@app.post("/papers/export")
async def export_papers(user_data = Depends(verify_user_and_check_limits)):
    """
    Export user's saved papers (premium feature only)
    Only premium/pro users can use this
    """
    user, limits = user_data
    
    if not limits.can_export:
        raise HTTPException(
            status_code=403, 
            detail="Export feature requires premium subscription"
        )
    
    try:
        result = supabase.table("saved_papers").select("*").eq("user_id", user.id).execute()
        
        return {
            "message": "Export ready",
            "papers": result.data,
            "format": "json"
        }
    
    except Exception as e:
        print(f"Export error: {e}")
        raise HTTPException(status_code=500, detail="Failed to export papers")

# Public endpoints (no authentication required)
@app.get("/")
async def root():
    """Basic health check"""
    return {"message": "Research Assistant API is running"}

@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "anthropic_key": "✓" if os.getenv("ANTHROPIC_API_KEY") else "✗",
        "pubmed_email": "✓" if os.getenv("PUBMED_EMAIL") else "✗",
        "supabase": "✓" if SUPABASE_URL and SUPABASE_KEY else "✗"
    }