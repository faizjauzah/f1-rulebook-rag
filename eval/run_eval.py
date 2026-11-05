import json
import sys
import time
from typing import List, Dict, Any
import requests

API_URL = "http://localhost:8000"


def load_questions(filepath: str = "eval/questions.json") -> List[Dict[str, Any]]:
    """Load evaluation questions from JSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def run_eval(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Run evaluation on all questions."""
    results = []
    
    for q in questions:
        print(f"\n{'='*80}")
        print(f"Question {q['id']} ({q['category']}) - Section {q['section']}")
        print(f"Q: {q['question']}")
        print(f"{'='*80}")
        
        try:
            start = time.time()
            response = requests.post(
                f"{API_URL}/query",
                json={"question": q['question']},
                timeout=60
            )
            elapsed = time.time() - start
            
            if response.status_code == 200:
                data = response.json()
                print(f"\nAnswer: {data['answer'][:200]}...")
                print(f"\nSources: {len(data['sources'])} chunks")
                print(f"Response time: {elapsed:.2f}s")
                
                results.append({
                    "question_id": q['id'],
                    "question": q['question'],
                    "category": q['category'],
                    "status": "success",
                    "answer": data['answer'],
                    "sources_count": len(data['sources']),
                    "response_time": elapsed,
                    "metadata": data['metadata']
                })
            else:
                print(f"\nError: {response.status_code} - {response.text}")
                results.append({
                    "question_id": q['id'],
                    "question": q['question'],
                    "category": q['category'],
                    "status": "error",
                    "error": response.text
                })
        
        except Exception as e:
            print(f"\nException: {e}")
            results.append({
                "question_id": q['id'],
                "question": q['question'],
                "category": q['category'],
                "status": "exception",
                "error": str(e)
            })
    
    return results


def print_summary(results: List[Dict[str, Any]]):
    """Print evaluation summary."""
    print(f"\n\n{'='*80}")
    print("EVALUATION SUMMARY")
    print(f"{'='*80}")
    
    total = len(results)
    success = len([r for r in results if r['status'] == 'success'])
    failed = total - success
    
    print(f"\nTotal questions: {total}")
    print(f"Successful: {success}")
    print(f"Failed: {failed}")
    
    if success > 0:
        avg_time = sum(r['response_time'] for r in results if r['status'] == 'success') / success
        print(f"Average response time: {avg_time:.2f}s")
    
    # By category
    print("\nBy category:")
    for category in ['easy', 'medium', 'hard']:
        cat_results = [r for r in results if r.get('category') == category]
        cat_success = len([r for r in cat_results if r['status'] == 'success'])
        print(f"  {category.capitalize()}: {cat_success}/{len(cat_results)}")


if __name__ == "__main__":
    print("Loading questions...")
    questions = load_questions()
    
    print(f"Running evaluation on {len(questions)} questions...\n")
    results = run_eval(questions)
    
    print_summary(results)
    
    # Save results
    output_file = "eval/results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to {output_file}")
