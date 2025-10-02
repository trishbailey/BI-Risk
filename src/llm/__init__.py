import openai
from typing import List, Dict, Any
from datetime import datetime

class OpenAIClient:
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"  # Cost-effective model for summarization
        self.max_tokens = 1500  # Limit to control costs

    def summarize_risks(self, findings: List[Dict[str, Any]], company_name: str) -> Dict[str, Any]:
        """
        Summarizes risk findings into a clean report.
        findings: List of risk dicts from database (e.g., [{'category': 'sanctions', 'severity': 'high', 'description': '...'}])
        Returns: Dict with summary sections and cost.
        """
        try:
            # Build prompt with findings
            findings_text = "\n".join([
                f"- {f['risk_category']}: {f['severity'].upper()} - {f['description']}"
                for f in findings if f.get('severity')  # Only include non-empty findings
            ])
            
            if not findings_text.strip():
                return {
                    "summary": f"No significant risks found for {company_name}. Proceed with standard due diligence.",
                    "recommendations": "Monitor for emerging risks.",
                    "overall_risk_score": "LOW",
                    "cost": 0.0
                }

            prompt = f"""
            You are an M&A risk assessment expert. Summarize the following risk findings for the company "{company_name}".
            
            Findings:
            {findings_text}
            
            Generate a concise report with:
            1. **Key Risks**: Bullet points of top 3-5 risks with severity.
            2. **Overall Risk Score**: LOW/MEDIUM/HIGH/CRITICAL (based on severity distribution).
            3. **Recommendations**: 2-4 actionable steps for mitigation.
            4. Keep it professional, objective, and under 800 words. Focus on M&A implications.
            """

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": "You are a concise risk analyst."},
                          {"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=0.3  # Low for factual output
            )

            content = response.choices[0].message.content.strip()
            cost = self._calculate_cost(response.usage.total_tokens)

            # Parse response into structured sections (simple split for now; can refine later)
            sections = self._parse_summary(content)

            return {
                "summary": sections.get("key_risks", content),
                "recommendations": sections.get("recommendations", "Review with legal team."),
                "overall_risk_score": sections.get("risk_score", "MEDIUM"),
                "full_report": content,
                "cost": cost
            }

        except Exception as e:
            # Fallback to basic summary
            return {
                "summary": f"Error generating summary: {str(e)}. Manual review required for {len(findings)} findings.",
                "recommendations": "Consult external experts.",
                "overall_risk_score": "UNKNOWN",
                "cost": 0.0
            }

    def _calculate_cost(self, tokens: int) -> float:
        """Rough cost estimate for gpt-4o-mini: $0.15/1M input + $0.60/1M output tokens."""
        input_cost = (tokens * 0.3) * 0.00015  # Assume ~70% input
        output_cost = (tokens * 0.7) * 0.00060
        return round(input_cost + output_cost, 4)

    def _parse_summary(self, content: str) -> Dict[str, str]:
        """Simple parser to extract sections from LLM output."""
        sections = {"key_risks": "", "recommendations": "", "risk_score": "MEDIUM"}
        lines = content.split("\n")
        current_section = None
        
        for line in lines:
            if "**Key Risks**" in line:
                current_section = "key_risks"
            elif "**Overall Risk Score**:" in line:
                sections["risk_score"] = line.split(":")[-1].strip().upper()
                current_section = None
            elif "**Recommendations**" in line:
                current_section = "recommendations"
            elif current_section:
                sections[current_section] += line + "\n"
        
        return {k: v.strip() for k, v in sections.items() if v.strip()}
