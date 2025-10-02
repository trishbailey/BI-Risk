import openai
from typing import List, Dict, Any
from datetime import datetime

class OpenAIClient:
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"  # Cost-effective for reports
        self.max_tokens = 1000  # Lower for concise facts

    def generate_full_report(self, findings: List[Dict[str, Any]], api_responses: List[Dict[str, Any]], company_name: str, industry: str) -> Dict[str, Any]:
        """
        Generates a factual, plain-language summary of findings and API data.
        No risk assessments—just the facts in narrative form.
        """
        try:
            # Build context from findings
            findings_text = "\n".join([
                f"- {f['risk_category']}: {f['description']} (Source: {f['source_api']})"
                for f in findings if f.get('severity')  # Only non-empty
            ])
            
            # Summarize API responses factually
            api_summary = "\n".join([
                f"- {r['api_name']}: {r['response_data'].get('status', 'unknown')}. {r['response_data'].get('summary', 'No details available.')}"
                for r in api_responses
            ])
            
            if not findings_text.strip() and not api_summary.strip():
                return {
                    "full_report": f"For {company_name} in the {industry} industry, no findings or details were identified in the checked sources.",
                    "cost": 0.0
                }

            prompt = f"""
            You are a factual reporter summarizing due diligence data for "{company_name}", a company in the {industry} industry.
            
            Stick to the facts only: List what was found in plain, simple English. Use short sentences and bullets. No opinions, risk levels, recommendations, or assessments—just describe the data.
            
            Key findings:
            {findings_text}
            
            API results:
            {api_summary}
            
            Output a concise briefing (under 500 words) in plain language, like a neutral memo:
            - Start with a one-sentence overview.
            - Use bullets for specific details from findings and APIs.
            - End with any notable dates or numbers.
            No JSON, tables, or bold headers—just readable text.
            """

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": "Write in clear, everyday language. Facts only—no analysis."},
                          {"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=0.1  # Very low for neutral, factual tone
            )

            content = response.choices[0].message.content.strip()
            cost = self._calculate_cost(response.usage.total_tokens)

            return {
                "full_report": content,
                "cost": cost
            }

        except Exception as e:
            return {
                "full_report": f"Unable to summarize: {str(e)}. {len(findings)} findings and {len(api_responses)} API results available for manual review.",
                "cost": 0.0
            }

    def _calculate_cost(self, tokens: int) -> float:
        """Estimate for gpt-4o-mini: ~$0.15/1M input + $0.60/1M output."""
        input_cost = (tokens * 0.6) * 0.00015
        output_cost = (tokens * 0.4) * 0.00060
        return round(input_cost + output_cost, 4)
