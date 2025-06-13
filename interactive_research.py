#!/usr/bin/env python3
"""
Interactive Research Assistant
Lets you type in different research questions
"""

import asyncio
from research_assistant import ResearchAssistant

async def main():
    """Interactive research question interface"""
    
    assistant = ResearchAssistant()
    
    print("Research Assistant - Interactive Mode")
    print("="*50)
    print("Type your research questions (or 'quit' to exit)")
    print()
    
    while True:
        # Get question from user
        question = input("Enter your research question: ").strip()
        
        if question.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break
        
        if not question:
            print("Please enter a question!")
            continue
        
        print(f"\nSearching for: '{question}'")
        print("-" * 60)
        
        try:
            # Process the question
            results = await assistant.process_research_question(question, max_papers=5)
            
            if not results:
                print("No papers found. Try rephrasing your question.")
                print()
                continue
            
            # Display results
            print(f"\nFound {len(results)} relevant papers:")
            print("=" * 60)
            
            for i, paper in enumerate(results, 1):
                print(f"\n{i}. {paper.title}")
                print(f"   Authors: {', '.join(paper.authors[:3])}")
                print(f"   Journal: {paper.journal} ({paper.year})")
                print(f"   Relevance: {paper.relevance_score}/10 - {paper.relevance_reason}")
                print(f"   Abstract: {paper.abstract[:200]}...")
                print(f"   Link: {paper.pubmed_url}")
            
            print("\n" + "=" * 60)
            print()
            
        except Exception as e:
            print(f"Error: {e}")
            print("Try a different question or check your API keys.")
            print()

if __name__ == "__main__":
    asyncio.run(main())