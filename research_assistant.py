#!/usr/bin/env python3
"""
Research Assistant Core Logic
Converts research questions to keywords, searches PubMed, and uses AI to rank results
"""

import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Tuple
import json
from dataclasses import dataclass
import os
from anthropic import Anthropic
from dotenv import load_dotenv
import asyncio

# Load environment variables from .env file
load_dotenv()

@dataclass
class Paper:
    title: str
    authors: List[str]
    abstract: str
    journal: str
    year: str
    pmid: str
    pubmed_url: str
    relevance_score: float = 0.0
    relevance_reason: str = ""

class ResearchAssistant:
    """Main class that orchestrates the research process"""
    
    def __init__(self):
        # Initialize APIs
        self.anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.pubmed_email = os.getenv("PUBMED_EMAIL", "your-email@university.edu")
        self.pubmed_api_key = os.getenv("PUBMED_API_KEY", "")
        self.pubmed_base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    
    async def process_research_question(self, question: str, max_papers: int = 10) -> List[Paper]:
        """
        Main workflow: question → keywords → search → AI ranking → results
        """
        print(f"Processing: {question}")
        
        # Step 1: Convert question to search keywords
        keywords = await self._extract_keywords(question)
        print(f"Keywords: {keywords}")
        
        # Step 2: Search PubMed
        papers = self._search_pubmed(keywords, max_papers * 2)  # Get more to filter
        print(f"Found {len(papers)} papers")
        
        if not papers:
            return []
        
        # Step 3: Use AI to rank papers by relevance
        ranked_papers = await self._rank_papers_by_relevance(question, papers)
        
        # Return top results
        return ranked_papers[:max_papers]
    
    async def _extract_keywords(self, question: str) -> str:
        """Use Claude to convert research question into PubMed search terms"""
        
        prompt = f"""
        Convert this research question into effective PubMed search keywords.
        
        Research Question: "{question}"
        
        Guidelines:
        - Use medical/scientific terminology when appropriate
        - Include 3-6 key terms
        - Use AND/OR operators if helpful
        - Focus on the main concepts
        - Consider synonyms for key terms
        
        Return only the search string, nothing else.
        
        Examples:
        "How does caffeine affect sleep quality?" → "caffeine AND sleep quality"
        "What are the benefits of meditation for anxiety?" → "meditation AND anxiety OR mindfulness therapy"
        """
        
        try:
            response = self.anthropic.messages.create(
                model="claude-3-5-sonnet-20241022",  # Updated to current model
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )
            
            keywords = response.content[0].text.strip()
            return keywords
            
        except Exception as e:
            print(f"Keyword extraction error: {e}")
            # Fallback: use the question as-is
            return question
    
    def _search_pubmed(self, keywords: str, max_results: int = 20) -> List[Paper]:
        """Search PubMed and return paper objects"""
        
        # Step 1: Search for paper IDs
        paper_ids = self._get_paper_ids(keywords, max_results)
        if not paper_ids:
            return []
        
        # Step 2: Fetch paper details
        return self._fetch_paper_details(paper_ids)
    
    def _get_paper_ids(self, keywords: str, max_results: int) -> List[str]:
        """Get list of paper IDs from PubMed search"""
        
        search_url = f"{self.pubmed_base_url}esearch.fcgi"
        params = {
            'db': 'pubmed',
            'term': keywords,
            'retmax': max_results,
            'retmode': 'xml',
            'email': self.pubmed_email,
            'api_key': self.pubmed_api_key,
            'sort': 'relevance'  # PubMed's built-in relevance sorting
        }
        
        try:
            response = requests.get(search_url, params=params, timeout=10)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            id_list = root.find('.//IdList')
            
            if id_list is not None:
                return [id_elem.text for id_elem in id_list.findall('Id')]
            return []
            
        except Exception as e:
            print(f"PubMed search error: {e}")
            return []
    
    def _fetch_paper_details(self, paper_ids: List[str]) -> List[Paper]:
        """Fetch detailed paper information"""
        
        if not paper_ids:
            return []
        
        fetch_url = f"{self.pubmed_base_url}efetch.fcgi"
        params = {
            'db': 'pubmed',
            'id': ','.join(paper_ids),
            'retmode': 'xml',
            'email': self.pubmed_email,
            'api_key': self.pubmed_api_key
        }
        
        try:
            response = requests.get(fetch_url, params=params, timeout=15)
            response.raise_for_status()
            
            papers = []
            root = ET.fromstring(response.content)
            
            for article in root.findall('.//PubmedArticle'):
                paper = self._parse_article_xml(article)
                if paper:
                    papers.append(paper)
            
            return papers
            
        except Exception as e:
            print(f"Paper fetch error: {e}")
            return []
    
    def _parse_article_xml(self, article_elem) -> Paper:
        """Parse XML for a single paper"""
        
        try:
            # Extract basic info
            title_elem = article_elem.find('.//ArticleTitle')
            title = title_elem.text if title_elem is not None else "No title"
            
            # Get abstract
            abstract_texts = []
            for abstract_elem in article_elem.findall('.//Abstract/AbstractText'):
                if abstract_elem.text:
                    abstract_texts.append(abstract_elem.text)
            abstract = " ".join(abstract_texts) if abstract_texts else "No abstract available"
            
            # Get authors (limit to first 5)
            authors = []
            for author in article_elem.findall('.//Author')[:5]:
                lastname = author.find('LastName')
                forename = author.find('ForeName')
                if lastname is not None:
                    name = lastname.text
                    if forename is not None:
                        name = f"{forename.text} {lastname.text}"
                    authors.append(name)
            
            # Get publication info
            year_elem = article_elem.find('.//PubDate/Year')
            year = year_elem.text if year_elem is not None else "Unknown"
            
            journal_elem = article_elem.find('.//Journal/Title')
            journal = journal_elem.text if journal_elem is not None else "Unknown journal"
            
            pmid_elem = article_elem.find('.//PMID')
            pmid = pmid_elem.text if pmid_elem is not None else "Unknown"
            
            return Paper(
                title=title,
                authors=authors,
                abstract=abstract,
                journal=journal,
                year=year,
                pmid=pmid,
                pubmed_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            )
            
        except Exception as e:
            print(f"XML parsing error: {e}")
            return None
    
    async def _rank_papers_by_relevance(self, original_question: str, papers: List[Paper]) -> List[Paper]:
        """Use Claude to analyze and rank papers by relevance to original question"""
        
        # Create a concise summary of each paper for analysis
        paper_summaries = []
        for i, paper in enumerate(papers):
            summary = {
                'index': i,
                'title': paper.title,
                'abstract': paper.abstract[:500] + "..." if len(paper.abstract) > 500 else paper.abstract,
                'year': paper.year
            }
            paper_summaries.append(summary)
        
        prompt = f"""
        Original Research Question: "{original_question}"
        
        Please analyze these research papers and rank them by relevance to the research question.
        For each paper, provide:
        1. A relevance score (0-10, where 10 is most relevant)
        2. A brief reason why it's relevant or not relevant
        
        Papers to analyze:
        {json.dumps(paper_summaries, indent=2)}
        
        Respond with a JSON array like this:
        [
          {{
            "index": 0,
            "relevance_score": 8.5,
            "reason": "Directly addresses the research question with recent data"
          }},
          {{
            "index": 1,
            "relevance_score": 6.0,
            "reason": "Related topic but focuses on different population"
          }}
        ]
        
        Return only the JSON array, no other text.
        """
        
        try:
            response = self.anthropic.messages.create(
                model="claude-3-5-sonnet-20241022",  # Updated to current model
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Parse the JSON response
            rankings_text = response.content[0].text.strip()
            rankings = json.loads(rankings_text)
            
            # Apply rankings to papers
            for ranking in rankings:
                paper_index = ranking['index']
                if 0 <= paper_index < len(papers):
                    papers[paper_index].relevance_score = ranking['relevance_score']
                    papers[paper_index].relevance_reason = ranking['reason']
            
            # Sort by relevance score (highest first)
            ranked_papers = sorted(papers, key=lambda p: p.relevance_score, reverse=True)
            return ranked_papers
            
        except Exception as e:
            print(f"Ranking error: {e}")
            # Fallback: return papers in original order
            return papers


# Testing functions - add these to test each component separately
async def test_keyword_extraction():
    """Test the keyword extraction function"""
    print("Testing keyword extraction...")
    
    assistant = ResearchAssistant()
    
    test_questions = [
        "How does caffeine affect sleep quality?",
        "What are the benefits of meditation for anxiety?",
        "Does exercise improve cognitive function in elderly?"
    ]
    
    for question in test_questions:
        print(f"\nQuestion: {question}")
        keywords = await assistant._extract_keywords(question)
        print(f"Keywords: {keywords}")

def test_pubmed_search():
    """Test PubMed search with manual keywords"""
    print("\nTesting PubMed search...")
    
    assistant = ResearchAssistant()
    
    test_keywords = [
        "caffeine AND sleep quality",
        "meditation AND anxiety",
        "exercise AND cognitive function"
    ]
    
    for keywords in test_keywords:
        print(f"\nSearching: {keywords}")
        papers = assistant._search_pubmed(keywords, max_results=5)
        print(f"Found {len(papers)} papers")
        
        if papers:
            print(f"First paper: {papers[0].title}")
            print(f"Journal: {papers[0].journal} ({papers[0].year})")

async def test_full_workflow():
    """Test the complete workflow"""
    print("\nTesting full workflow...")
    
    assistant = ResearchAssistant()
    
    question = "How does social media use affect sleep quality in teenagers?"
    
    try:
        results = await assistant.process_research_question(question, max_papers=3)
        
        print(f"\nResults for: '{question}'\n" + "="*50)
        
        for i, paper in enumerate(results, 1):
            print(f"\n{i}. {paper.title}")
            print(f"   Authors: {', '.join(paper.authors[:3])}")
            print(f"   Journal: {paper.journal} ({paper.year})")
            print(f"   Relevance: {paper.relevance_score}/10 - {paper.relevance_reason}")
            print(f"   Abstract: {paper.abstract[:200]}...")
            print(f"   Link: {paper.pubmed_url}")
            
    except Exception as e:
        print(f"Error in full workflow: {e}")

# Main function for testing
async def main():
    """Run all tests"""
    print("Starting Research Assistant Tests\n" + "="*50)
    
    # Test 1: Keyword extraction
    await test_keyword_extraction()
    
    # Test 2: PubMed search
    test_pubmed_search()
    
    # Test 3: Full workflow
    await test_full_workflow()

if __name__ == "__main__":
    asyncio.run(main())