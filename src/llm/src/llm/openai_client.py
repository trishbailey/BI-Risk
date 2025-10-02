import openai
from typing import List, Dict, Any
from datetime import datetime

class OpenAIClient:
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"  # Cost-effective for reports
        self.max_tokens = 2000  # Slightly higher for full reports

    def generate_full_report(self, findings: List[Dict[str, Any]], api_responses: List[Dict[str, Any]], company_name: str, industry: str) -> Dict[str, Any]:
        """
        Generates a comprehensive M&A risk report from all findings and API data.
        findings: List from db.get_assessment_findings()
        api_responses: List from db.get_api_responses()
        Returns: Dict with report sections and cost.
        """
        try:
            # Build context from findings
            findings_text = "\n".join([
                f"- {f['risk_category']}: {f['severity'].upper()} - {f['description']} (Source: {f['source_api']})"
                for f in findings if f.get('severity')  # Only non-empty
            ])
            
            # Summarize API responses
            api_summary = "\n".join([
                f"- {r['api_name']}: {r['response_data'].get('status', 'unknown')} ({r['response_data'].get('summary', 'No summary')})"
                for r in api_responses
            ])
            
            if not findings_text.strip() and not api_summary.strip():
                return {
                    "full_report": f"No significant risks identified for {company_name} ({industry}). Proceed with standard due diligence.",
                    "key_risks": "None",
                    "recommendations": "Conduct routine post-merger integration monitoring.",
                    "overall_risk_score": "LOW",
                    "cost": 0.0
                }

            prompt = f"""
            You are an expert M&A risk analyst. Generate a professional report for the potential acquisition of "{company_name}" in the {industry} industry.
            
            Risk Findings:
            {findings_text}
            
            API Check Summaries:
            {api_summary}
            
            Structure the report as:
            1. **Executive Summary**: 2-3 sentences on overall risk profile and M&A implications.
            2. **Key Risks**: Bullet points of top 3-5 risks, including severity and potential deal impact.
            3. **Overall Risk Score**: LOW/MEDIUM/HIGH/CRITICAL (based on findings distribution).
            4. **Recommendations**: 3-5 actionable mitigation steps, prioritized by severity.
            5. **Next Steps**: Suggested follow-up due diligence areas.
            
            Keep concise (under 1000 words), objective, and focused on M&A risks. Use markdown for formatting.
            """

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": "You are a precise, professional risk consultant."},
                          {"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=0.2  # Low for consistent, factual output
            )

            content = response.choices[0].message.content.strip()
            cost = self._calculate_cost(response.usage.total_tokens)

            # Simple parsing for sections (can enhance with regex if needed)
            sections = self._parse_report(content)

            return {
                "full_report": content,
                "key_risks": sections.get("key_risks", "See full report."),
                "recommendations": sections.get("recommendations", "Review with legal/financial teams."),
                "overall_risk_score": sections.get("risk_score", "MEDIUM"),
                "cost": cost
            }

        except Exception as e:
            return {
                "full_report": f"Error generating report: {str(e)}. Manual review of {len(findings)} findings required for {company_name}.",
                "key_risks": "Error - see findings above.",
                "recommendations": "Immediate expert consultation.",
                "overall_risk_score": "UNKNOWN",
                "cost": 0.0
            }

    def _calculate_cost(self, tokens: int) -> float:
        """Estimate for gpt-4o-mini: ~$0.15/1M input + $0.60/1M output."""
        input_cost = (tokens * 0.6) * 0.00015
        output_cost = (tokens * 0.4) * 0.00060
        return round(input_cost + output_cost, 4)

    def _parse_report(self, content: str) -> Dict[str, str]:
        """Extract sections from LLM output."""
        sections = {"key_risks": "", "recommendations": "", "risk_score": "MEDIUM"}
        lines = content.split("\n")
        current_section = None
        
        for line in lines:
            line = line.strip()
            if "**Executive Summary**" in line:
                current_section = None
            elif "**Key Risks**" in line:
                current_section = "key_risks"
            elif "**Overall Risk Score**" in line:
                sections["risk_score"] = line.split(":")[-1].strip().upper() if ":" in line else "MEDIUM"
                current_section = None
            elif "**Recommendations**" in line:
                current_section = "recommendations"
            elif "**Next Steps**" in line:
                current_section = None
            elif current_section and line:
                sections[current_section] += line + "\n"
        
        return {k: v.strip() for k, v in sections.items() if v.strip()}
