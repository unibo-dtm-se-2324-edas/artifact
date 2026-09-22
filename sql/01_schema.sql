CREATE TABLE IF NOT EXISTS countries (
    country_code VARCHAR(2) PRIMARY KEY, -- ISO 3166-1 alpha-2 code
    country_name VARCHAR(50) NOT NULL,
    zone_key VARCHAR(16) NOT NULL        -- ENTSO-E specific zone identifier
);

CREATE TABLE IF NOT EXISTS energy_production (
    production_id SERIAL PRIMARY KEY,
    country_code VARCHAR(2) NOT NULL,
    time_stamp TIMESTAMP NOT NULL,
    source_type VARCHAR(50) NOT NULL,    -- e.g., 'Nuclear', 'Solar', 'Hydro'
    production_mw DOUBLE PRECISION NOT NULL,
    
    -- Ensures idempotency: one value per country, timestamp, and source.
    UNIQUE (country_code, time_stamp, source_type)
);

CREATE TABLE IF NOT EXISTS energy_consumption (
    consumption_id SERIAL PRIMARY KEY,
    country_code VARCHAR(2) NOT NULL REFERENCES countries(country_code),
    time_stamp TIMESTAMP NOT NULL,
    consumption_mw DOUBLE PRECISION NOT NULL,
    
    -- Ensures idempotency: one value per country and timestamp.
    UNIQUE (country_code, time_stamp)
);

CREATE TABLE IF NOT EXISTS cross_border_flow (
    flow_id SERIAL PRIMARY KEY,
    from_country_code VARCHAR(2) NOT NULL REFERENCES countries(country_code),
    to_country_code   VARCHAR(2) NOT NULL REFERENCES countries(country_code),
    time_stamp        TIMESTAMP NOT NULL,
    flow_mw           DOUBLE PRECISION NOT NULL, -- Net flow value
    
    -- Ensures idempotency: one value per direction and timestamp.
    UNIQUE (from_country_code, to_country_code, time_stamp)
);

-- Insert lookup data for the countries specified in the project scope.
-- ON CONFLICT DO NOTHING ensures this operation is idempotent and safe to run multiple times.
INSERT INTO countries (country_code, country_name, zone_key) VALUES
        ('FR', 'France', '10YFR-RTE------C'),
        ('DE', 'Germany', '10Y1001A1001A83F'),
        ('BE', 'Belgium', '10YBE----------2'),
        ('CH', 'Switzerland', '10YCH-SWISSGRIDZ'),
        ('ES', 'Spain', '10YES-REE------0'),
        ('NL', 'Netherlands', '10YNL----------L'),
        ('AT', 'Austria', '10YAT-APG------L'),
        ('CZ', 'Czech Republic', '10YCZ-CEPS-----N'),
        ('PL', 'Poland', '10YPL-AREA-----S')
ON CONFLICT (country_code) DO NOTHING;