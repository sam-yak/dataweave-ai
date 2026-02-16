-- ============================================
-- DataWeave AI — Database Schema
-- Run this in Supabase SQL Editor
-- ============================================

-- 1. TARGET SCHEMAS
-- Stores the target formats users can map data into
CREATE TABLE target_schemas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    schema_json JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. JOBS
-- Each file upload creates one job that moves through the pipeline
CREATE TABLE jobs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'uploaded',
    original_filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size_bytes INTEGER,
    row_count INTEGER,
    column_count INTEGER,
    target_schema_id UUID REFERENCES target_schemas(id),
    quality_score REAL,
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT valid_status CHECK (status IN (
        'uploaded', 'ingesting', 'profiling', 'mapping',
        'awaiting_review', 'transforming', 'validating',
        'complete', 'failed'
    ))
);

-- 3. COLUMNS
-- Every column detected in the uploaded file
CREATE TABLE columns (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    detected_type TEXT,
    sample_values JSONB DEFAULT '[]',
    null_count INTEGER DEFAULT 0,
    total_count INTEGER DEFAULT 0,
    unique_count INTEGER DEFAULT 0,
    profile_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. MAPPINGS
-- AI-proposed (and human-reviewed) column mappings
CREATE TABLE mappings (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    column_id UUID REFERENCES columns(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    target_field TEXT,
    confidence REAL DEFAULT 0,
    transform_type TEXT,
    transform_config JSONB DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'proposed',
    agent_source TEXT NOT NULL DEFAULT 'schema',
    reasoning TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT valid_mapping_status CHECK (status IN (
        'proposed', 'approved', 'rejected', 'corrected'
    )),
    CONSTRAINT valid_agent_source CHECK (agent_source IN (
        'pattern', 'schema', 'manual'
    ))
);

-- 5. PATTERNS
-- The learning memory — stores known column mappings that improve over time
CREATE TABLE patterns (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    target_schema_id UUID REFERENCES target_schemas(id) ON DELETE CASCADE,
    source_name_normalized TEXT NOT NULL,
    target_field TEXT NOT NULL,
    transform_type TEXT,
    transform_config JSONB DEFAULT '{}',
    approval_count INTEGER DEFAULT 0,
    rejection_count INTEGER DEFAULT 0,
    confidence REAL DEFAULT 0.5,
    last_used_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(target_schema_id, source_name_normalized, target_field)
);

-- 6. EVENTS
-- Agent activity log — powers the real-time activity panel in the UI
CREATE TABLE events (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    agent TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. WAITLIST
-- Email captures from the landing page
CREATE TABLE waitlist (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    source TEXT DEFAULT 'landing_page',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- INDEXES — Speed up the queries we'll run most
-- ============================================

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created ON jobs(created_at DESC);
CREATE INDEX idx_columns_job ON columns(job_id);
CREATE INDEX idx_mappings_job ON mappings(job_id);
CREATE INDEX idx_mappings_status ON mappings(status);
CREATE INDEX idx_patterns_lookup ON patterns(target_schema_id, source_name_normalized);
CREATE INDEX idx_patterns_confidence ON patterns(confidence DESC);
CREATE INDEX idx_events_job ON events(job_id);
CREATE INDEX idx_events_created ON events(created_at DESC);

-- ============================================
-- AUTO-UPDATE updated_at TRIGGER
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER jobs_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER mappings_updated_at
    BEFORE UPDATE ON mappings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- SEED DATA — 3 Target Schemas
-- ============================================

INSERT INTO target_schemas (name, description, schema_json) VALUES

('Generic CRM Contact', 'Standard contact format compatible with most CRM systems', '{
    "fields": [
        {"name": "first_name", "type": "string", "required": true},
        {"name": "last_name", "type": "string", "required": true},
        {"name": "email", "type": "string", "required": true, "format": "email", "unique": true},
        {"name": "phone", "type": "string", "required": false, "format": "phone"},
        {"name": "company", "type": "string", "required": false},
        {"name": "job_title", "type": "string", "required": false},
        {"name": "address", "type": "string", "required": false},
        {"name": "city", "type": "string", "required": false},
        {"name": "state", "type": "string", "required": false},
        {"name": "zip_code", "type": "string", "required": false, "format": "zipcode"},
        {"name": "country", "type": "string", "required": false},
        {"name": "website", "type": "string", "required": false, "format": "url"},
        {"name": "source", "type": "string", "required": false},
        {"name": "notes", "type": "string", "required": false},
        {"name": "created_at", "type": "date", "required": false, "format": "iso8601"}
    ]
}'),

('HubSpot Contact Import', 'HubSpot-compatible contact format for direct import', '{
    "fields": [
        {"name": "firstname", "type": "string", "required": true},
        {"name": "lastname", "type": "string", "required": true},
        {"name": "email", "type": "string", "required": true, "format": "email", "unique": true},
        {"name": "phone", "type": "string", "required": false, "format": "phone"},
        {"name": "company", "type": "string", "required": false},
        {"name": "jobtitle", "type": "string", "required": false},
        {"name": "address", "type": "string", "required": false},
        {"name": "city", "type": "string", "required": false},
        {"name": "state", "type": "string", "required": false},
        {"name": "zip", "type": "string", "required": false, "format": "zipcode"},
        {"name": "country", "type": "string", "required": false},
        {"name": "website", "type": "string", "required": false, "format": "url"},
        {"name": "lifecyclestage", "type": "string", "required": false, "enum": ["subscriber", "lead", "marketingqualifiedlead", "salesqualifiedlead", "opportunity", "customer", "evangelist"]},
        {"name": "hs_lead_status", "type": "string", "required": false},
        {"name": "hubspot_owner_id", "type": "string", "required": false}
    ]
}'),

('Stripe Customer Import', 'Stripe-compatible customer format for API import', '{
    "fields": [
        {"name": "name", "type": "string", "required": true},
        {"name": "email", "type": "string", "required": true, "format": "email", "unique": true},
        {"name": "phone", "type": "string", "required": false, "format": "phone"},
        {"name": "description", "type": "string", "required": false},
        {"name": "address_line1", "type": "string", "required": false},
        {"name": "address_line2", "type": "string", "required": false},
        {"name": "address_city", "type": "string", "required": false},
        {"name": "address_state", "type": "string", "required": false},
        {"name": "address_postal_code", "type": "string", "required": false, "format": "zipcode"},
        {"name": "address_country", "type": "string", "required": false},
        {"name": "currency", "type": "string", "required": false, "default": "usd"},
        {"name": "balance", "type": "integer", "required": false, "description": "Balance in cents"},
        {"name": "metadata", "type": "string", "required": false, "description": "JSON string of key-value pairs"}
    ]
}');

-- ============================================
-- SEED DATA — 100+ Common Patterns
-- ============================================

-- We need the schema IDs to link patterns. This uses a DO block to fetch them.
DO $$
DECLARE
    crm_id UUID;
    hubspot_id UUID;
    stripe_id UUID;
BEGIN
    SELECT id INTO crm_id FROM target_schemas WHERE name = 'Generic CRM Contact';
    SELECT id INTO hubspot_id FROM target_schemas WHERE name = 'HubSpot Contact Import';
    SELECT id INTO stripe_id FROM target_schemas WHERE name = 'Stripe Customer Import';

    -- ========== GENERIC CRM PATTERNS ==========
    -- Name fields
    INSERT INTO patterns (target_schema_id, source_name_normalized, target_field, confidence, approval_count) VALUES
    (crm_id, 'firstname', 'first_name', 0.95, 10),
    (crm_id, 'first_name', 'first_name', 0.99, 20),
    (crm_id, 'fname', 'first_name', 0.90, 8),
    (crm_id, 'first', 'first_name', 0.85, 5),
    (crm_id, 'givenname', 'first_name', 0.90, 6),
    (crm_id, 'given_name', 'first_name', 0.92, 7),
    (crm_id, 'lastname', 'last_name', 0.95, 10),
    (crm_id, 'last_name', 'last_name', 0.99, 20),
    (crm_id, 'lname', 'last_name', 0.90, 8),
    (crm_id, 'last', 'last_name', 0.85, 5),
    (crm_id, 'surname', 'last_name', 0.92, 7),
    (crm_id, 'familyname', 'last_name', 0.90, 6),
    (crm_id, 'family_name', 'last_name', 0.92, 7),
    -- Email fields
    (crm_id, 'email', 'email', 0.99, 25),
    (crm_id, 'emailaddress', 'email', 0.95, 12),
    (crm_id, 'email_address', 'email', 0.95, 12),
    (crm_id, 'mail', 'email', 0.88, 6),
    (crm_id, 'e_mail', 'email', 0.90, 5),
    (crm_id, 'primaryemail', 'email', 0.90, 5),
    -- Phone fields
    (crm_id, 'phone', 'phone', 0.99, 20),
    (crm_id, 'phonenumber', 'phone', 0.95, 12),
    (crm_id, 'phone_number', 'phone', 0.95, 12),
    (crm_id, 'tel', 'phone', 0.88, 6),
    (crm_id, 'telephone', 'phone', 0.90, 8),
    (crm_id, 'mobile', 'phone', 0.85, 5),
    (crm_id, 'cell', 'phone', 0.85, 5),
    (crm_id, 'cellphone', 'phone', 0.88, 5),
    -- Company fields
    (crm_id, 'company', 'company', 0.99, 20),
    (crm_id, 'companyname', 'company', 0.95, 12),
    (crm_id, 'company_name', 'company', 0.95, 12),
    (crm_id, 'organization', 'company', 0.90, 8),
    (crm_id, 'org', 'company', 0.82, 4),
    (crm_id, 'employer', 'company', 0.85, 5),
    -- Job title fields
    (crm_id, 'jobtitle', 'job_title', 0.95, 10),
    (crm_id, 'job_title', 'job_title', 0.99, 15),
    (crm_id, 'title', 'job_title', 0.80, 5),
    (crm_id, 'position', 'job_title', 0.85, 6),
    (crm_id, 'role', 'job_title', 0.78, 4),
    (crm_id, 'designation', 'job_title', 0.82, 4),
    -- Address fields
    (crm_id, 'address', 'address', 0.95, 12),
    (crm_id, 'streetaddress', 'address', 0.92, 8),
    (crm_id, 'street_address', 'address', 0.92, 8),
    (crm_id, 'street', 'address', 0.88, 6),
    (crm_id, 'address1', 'address', 0.90, 7),
    (crm_id, 'addressline1', 'address', 0.90, 7),
    (crm_id, 'city', 'city', 0.99, 20),
    (crm_id, 'town', 'city', 0.85, 5),
    (crm_id, 'municipality', 'city', 0.80, 3),
    (crm_id, 'state', 'state', 0.95, 15),
    (crm_id, 'province', 'state', 0.88, 6),
    (crm_id, 'region', 'state', 0.80, 4),
    (crm_id, 'stateprovince', 'state', 0.90, 5),
    (crm_id, 'state_province', 'state', 0.90, 5),
    (crm_id, 'zip', 'zip_code', 0.95, 12),
    (crm_id, 'zipcode', 'zip_code', 0.95, 12),
    (crm_id, 'zip_code', 'zip_code', 0.99, 15),
    (crm_id, 'postalcode', 'zip_code', 0.92, 8),
    (crm_id, 'postal_code', 'zip_code', 0.92, 8),
    (crm_id, 'postcode', 'zip_code', 0.90, 7),
    (crm_id, 'country', 'country', 0.99, 20),
    (crm_id, 'countrycode', 'country', 0.85, 5),
    (crm_id, 'country_code', 'country', 0.85, 5),
    -- Website fields
    (crm_id, 'website', 'website', 0.99, 15),
    (crm_id, 'url', 'website', 0.90, 8),
    (crm_id, 'web', 'website', 0.85, 5),
    (crm_id, 'homepage', 'website', 0.85, 5),
    (crm_id, 'domain', 'website', 0.78, 4),
    -- Source fields
    (crm_id, 'source', 'source', 0.95, 10),
    (crm_id, 'leadsource', 'source', 0.92, 8),
    (crm_id, 'lead_source', 'source', 0.92, 8),
    (crm_id, 'channel', 'source', 0.80, 4),
    (crm_id, 'referral', 'source', 0.75, 3),
    -- Notes fields
    (crm_id, 'notes', 'notes', 0.95, 10),
    (crm_id, 'comments', 'notes', 0.88, 6),
    (crm_id, 'description', 'notes', 0.82, 5),
    (crm_id, 'memo', 'notes', 0.80, 4),
    -- Date fields
    (crm_id, 'createdat', 'created_at', 0.92, 8),
    (crm_id, 'created_at', 'created_at', 0.99, 15),
    (crm_id, 'datecreated', 'created_at', 0.90, 7),
    (crm_id, 'date_created', 'created_at', 0.90, 7),
    (crm_id, 'createddate', 'created_at', 0.90, 7),
    (crm_id, 'created_date', 'created_at', 0.90, 7),
    (crm_id, 'date', 'created_at', 0.70, 3),
    (crm_id, 'timestamp', 'created_at', 0.75, 4);

    -- ========== HUBSPOT PATTERNS ==========
    INSERT INTO patterns (target_schema_id, source_name_normalized, target_field, confidence, approval_count) VALUES
    (hubspot_id, 'firstname', 'firstname', 0.99, 20),
    (hubspot_id, 'first_name', 'firstname', 0.95, 12),
    (hubspot_id, 'fname', 'firstname', 0.90, 8),
    (hubspot_id, 'first', 'firstname', 0.85, 5),
    (hubspot_id, 'givenname', 'firstname', 0.90, 6),
    (hubspot_id, 'lastname', 'lastname', 0.99, 20),
    (hubspot_id, 'last_name', 'lastname', 0.95, 12),
    (hubspot_id, 'lname', 'lastname', 0.90, 8),
    (hubspot_id, 'last', 'lastname', 0.85, 5),
    (hubspot_id, 'surname', 'lastname', 0.92, 7),
    (hubspot_id, 'email', 'email', 0.99, 25),
    (hubspot_id, 'emailaddress', 'email', 0.95, 12),
    (hubspot_id, 'email_address', 'email', 0.95, 12),
    (hubspot_id, 'phone', 'phone', 0.99, 20),
    (hubspot_id, 'phonenumber', 'phone', 0.95, 12),
    (hubspot_id, 'telephone', 'phone', 0.90, 8),
    (hubspot_id, 'mobile', 'phone', 0.85, 5),
    (hubspot_id, 'company', 'company', 0.99, 20),
    (hubspot_id, 'companyname', 'company', 0.95, 12),
    (hubspot_id, 'organization', 'company', 0.90, 8),
    (hubspot_id, 'jobtitle', 'jobtitle', 0.99, 15),
    (hubspot_id, 'job_title', 'jobtitle', 0.95, 12),
    (hubspot_id, 'title', 'jobtitle', 0.80, 5),
    (hubspot_id, 'position', 'jobtitle', 0.85, 6),
    (hubspot_id, 'city', 'city', 0.99, 20),
    (hubspot_id, 'state', 'state', 0.95, 15),
    (hubspot_id, 'province', 'state', 0.88, 6),
    (hubspot_id, 'zip', 'zip', 0.99, 15),
    (hubspot_id, 'zipcode', 'zip', 0.95, 12),
    (hubspot_id, 'postalcode', 'zip', 0.92, 8),
    (hubspot_id, 'country', 'country', 0.99, 20),
    (hubspot_id, 'website', 'website', 0.99, 15),
    (hubspot_id, 'url', 'website', 0.90, 8),
    (hubspot_id, 'lifecyclestage', 'lifecyclestage', 0.99, 10),
    (hubspot_id, 'lifecycle_stage', 'lifecyclestage', 0.95, 8),
    (hubspot_id, 'stage', 'lifecyclestage', 0.75, 3),
    (hubspot_id, 'leadstatus', 'hs_lead_status', 0.92, 8),
    (hubspot_id, 'lead_status', 'hs_lead_status', 0.92, 8),
    (hubspot_id, 'status', 'hs_lead_status', 0.70, 3);

    -- ========== STRIPE PATTERNS ==========
    INSERT INTO patterns (target_schema_id, source_name_normalized, target_field, confidence, approval_count) VALUES
    (stripe_id, 'name', 'name', 0.95, 15),
    (stripe_id, 'fullname', 'name', 0.92, 10),
    (stripe_id, 'full_name', 'name', 0.92, 10),
    (stripe_id, 'customername', 'name', 0.90, 8),
    (stripe_id, 'customer_name', 'name', 0.90, 8),
    (stripe_id, 'email', 'email', 0.99, 25),
    (stripe_id, 'emailaddress', 'email', 0.95, 12),
    (stripe_id, 'phone', 'phone', 0.99, 20),
    (stripe_id, 'phonenumber', 'phone', 0.95, 12),
    (stripe_id, 'description', 'description', 0.92, 8),
    (stripe_id, 'notes', 'description', 0.80, 5),
    (stripe_id, 'address', 'address_line1', 0.88, 6),
    (stripe_id, 'address1', 'address_line1', 0.92, 8),
    (stripe_id, 'addressline1', 'address_line1', 0.92, 8),
    (stripe_id, 'street', 'address_line1', 0.85, 5),
    (stripe_id, 'address2', 'address_line2', 0.92, 8),
    (stripe_id, 'addressline2', 'address_line2', 0.92, 8),
    (stripe_id, 'apt', 'address_line2', 0.80, 4),
    (stripe_id, 'suite', 'address_line2', 0.80, 4),
    (stripe_id, 'city', 'address_city', 0.95, 12),
    (stripe_id, 'town', 'address_city', 0.85, 5),
    (stripe_id, 'state', 'address_state', 0.95, 12),
    (stripe_id, 'province', 'address_state', 0.88, 6),
    (stripe_id, 'zip', 'address_postal_code', 0.95, 12),
    (stripe_id, 'zipcode', 'address_postal_code', 0.95, 12),
    (stripe_id, 'postalcode', 'address_postal_code', 0.92, 8),
    (stripe_id, 'country', 'address_country', 0.99, 15),
    (stripe_id, 'countrycode', 'address_country', 0.85, 5),
    (stripe_id, 'currency', 'currency', 0.95, 10),
    (stripe_id, 'currencycode', 'currency', 0.90, 7),
    (stripe_id, 'balance', 'balance', 0.92, 8),
    (stripe_id, 'amount', 'balance', 0.75, 4),
    (stripe_id, 'accountbalance', 'balance', 0.90, 6);

END $$;

-- ============================================
-- VERIFICATION — Run after to confirm everything worked
-- ============================================

-- Check table counts
SELECT 'target_schemas' as table_name, COUNT(*) as row_count FROM target_schemas
UNION ALL
SELECT 'patterns', COUNT(*) FROM patterns
UNION ALL
SELECT 'jobs', COUNT(*) FROM jobs
UNION ALL
SELECT 'columns', COUNT(*) FROM columns
UNION ALL
SELECT 'mappings', COUNT(*) FROM mappings
UNION ALL
SELECT 'events', COUNT(*) FROM events
UNION ALL
SELECT 'waitlist', COUNT(*) FROM waitlist;
