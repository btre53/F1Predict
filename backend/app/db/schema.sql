-- F1Predict PostgreSQL schema (era-partitioned).
-- Mirrors the original research doc section 1, with corrections from
-- docs/science/04-spec-validation.md folded in.

CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Regulatory eras. 2026 parameters are projections (low confidence).
DO $$ BEGIN
    CREATE TYPE regulation_era AS ENUM ('GE_DRS_2022_2025', 'ACTIVE_AERO_2026');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE tire_compound AS ENUM
        ('SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE track_status AS ENUM ('GREEN', 'VSC', 'SAFETY_CAR', 'RED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Circuits: per-circuit calibrated constants (replaces global hardcoded values).
CREATE TABLE IF NOT EXISTS circuits (
    circuit_key            INT PRIMARY KEY,
    name                   VARCHAR(100) NOT NULL,
    country                VARCHAR(100),
    base_lap_time_ms       INT,
    total_laps             INT,
    pit_loss_green_s       FLOAT,            -- decomposed total under green
    sc_base_rate           FLOAT DEFAULT 1.0 -- multiplier on SC count distribution
);

CREATE TABLE IF NOT EXISTS sessions (
    session_key            INT PRIMARY KEY,
    meeting_key            INT NOT NULL,
    season                 INT NOT NULL,
    session_name           VARCHAR(50) NOT NULL,   -- FP1/FP2/FP3/Q/Sprint/R
    circuit_key            INT NOT NULL REFERENCES circuits(circuit_key),
    regulation_era         regulation_era NOT NULL,
    total_laps             INT,
    base_lap_time_ms       INT,
    fuel_decay_coeff_ms_per_kg FLOAT,             -- era-specific
    created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS drivers (
    driver_number          INT PRIMARY KEY,
    driver_acronym         CHAR(3) NOT NULL,
    driver_name            VARCHAR(100) NOT NULL,
    team_name              VARCHAR(100),
    team_colour            CHAR(6),
    driver_skill_index     FLOAT NOT NULL DEFAULT 0.0,  -- era-invariant latent skill
    updated_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stints (
    stint_id               SERIAL PRIMARY KEY,
    session_key            INT REFERENCES sessions(session_key),
    driver_number          INT REFERENCES drivers(driver_number),
    stint_number           INT NOT NULL,
    compound               tire_compound NOT NULL,
    tyre_age_at_start      INT NOT NULL DEFAULT 0,
    start_lap              INT NOT NULL,
    end_lap                INT,
    is_used_set            BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (session_key, driver_number, stint_number)
);

-- Lap-by-lap state projection table.
CREATE TABLE IF NOT EXISTS laps (
    lap_id                 BIGSERIAL PRIMARY KEY,
    session_key            INT REFERENCES sessions(session_key),
    driver_number          INT REFERENCES drivers(driver_number),
    lap_number             INT NOT NULL,
    stint_id               INT REFERENCES stints(stint_id),
    lap_time_ms            INT,
    fuel_corrected_ms      INT,           -- derived in ETL
    fuel_remaining_kg      FLOAT,
    battery_soc_joules     DOUBLE PRECISION,   -- 2026 ERS state
    tyre_age_laps          INT NOT NULL,
    tyre_wear_index        FLOAT,         -- latent [0,1]
    compound               tire_compound,
    position               INT,
    gap_ahead_s            FLOAT,
    track_status           track_status NOT NULL DEFAULT 'GREEN',
    is_valid_for_calibration BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (session_key, driver_number, lap_number)
);

-- Calibrated era/circuit/compound tyre-degradation parameters (3-phase curve).
CREATE TABLE IF NOT EXISTS tyre_degradation_parameters (
    parameter_id           SERIAL PRIMARY KEY,
    circuit_key            INT NOT NULL,
    regulation_era         regulation_era NOT NULL,
    compound               tire_compound NOT NULL,
    theta_1 FLOAT, theta_2 FLOAT, theta_3 FLOAT,   -- warm-up + linear
    theta_4 FLOAT, theta_5 FLOAT, theta_6 FLOAT,   -- cliff
    pace_offset_s          FLOAT DEFAULT 0.0,
    fit_n_laps             INT,                     -- data support (for confidence)
    is_empirically_validated BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (circuit_key, regulation_era, compound)
);

-- Era-specific aerodynamic wake calibrations.
CREATE TABLE IF NOT EXISTS wake_calibrations (
    regulation_era         regulation_era PRIMARY KEY,
    mu_coefficient         FLOAT NOT NULL,
    lambda_coefficient     FLOAT NOT NULL,
    is_empirically_validated BOOLEAN NOT NULL DEFAULT FALSE
);

-- Indexes for fast lap-by-lap reads.
CREATE UNIQUE INDEX IF NOT EXISTS idx_laps_state_transition
    ON laps (session_key, driver_number, lap_number)
    INCLUDE (fuel_remaining_kg, tyre_age_laps, tyre_wear_index);

CREATE INDEX IF NOT EXISTS idx_stints_lookup
    ON stints (session_key, driver_number, stint_number);
