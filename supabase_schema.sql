-- Run this SQL in your Supabase SQL editor to create the tables

-- Main assessment table
CREATE TABLE assessments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    company_name TEXT NOT NULL,
    industry TEXT,
    status TEXT DEFAULT 'started',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by TEXT,
    total_cost DECIMAL(10,2) DEFAULT 0
);

-- Store raw API responses
CREATE TABLE api_responses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    assessment_id UUID REFERENCES assessments(id) ON DELETE CASCADE,
    api_name TEXT NOT NULL,
    response_data JSONB,
    api_cost DECIMAL(10,2) DEFAULT 0,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Risk findings from analysis
CREATE TABLE risk_findings (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    assessment_id UUID REFERENCES assessments(id) ON DELETE CASCADE,
    risk_category TEXT NOT NULL,
    severity TEXT CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    description TEXT,
    source_api TEXT,
    raw_data JSONB
);

-- Generated report sections
CREATE TABLE report_sections (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    assessment_id UUID REFERENCES assessments(id) ON DELETE CASCADE,
    section_name TEXT NOT NULL,
    content TEXT,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX idx_assessments_company_name ON assessments(company_name);
CREATE INDEX idx_assessments_status ON assessments(status);
CREATE INDEX idx_api_responses_assessment_id ON api_responses(assessment_id);
CREATE INDEX idx_api_responses_api_name ON api_responses(api_name);
CREATE INDEX idx_risk_findings_assessment_id ON risk_findings(assessment_id);
CREATE INDEX idx_risk_findings_severity ON risk_findings(severity);
CREATE INDEX idx_report_sections_assessment_id ON report_sections(assessment_id);

-- Enable Row Level Security (optional but recommended)
ALTER TABLE assessments ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE risk_findings ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_sections ENABLE ROW LEVEL SECURITY;

-- Create a policy that allows all operations for authenticated users
-- (You can make this more restrictive based on your needs)
CREATE POLICY "Enable all access for authenticated users" ON assessments
    FOR ALL USING (true);

CREATE POLICY "Enable all access for authenticated users" ON api_responses
    FOR ALL USING (true);

CREATE POLICY "Enable all access for authenticated users" ON risk_findings
    FOR ALL USING (true);

CREATE POLICY "Enable all access for authenticated users" ON report_sections
    FOR ALL USING (true);
