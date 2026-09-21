#!/usr/bin/env bash
# --------------------------------------------------------------------------
# DATABASE INITIALIZATION SCRIPT (DDL Execution)
# This script executes the DDL (schema creation) using the psql client.
# It ensures the database structure is ready before data ingestion (Part 1).
# --------------------------------------------------------------------------

# Set script to "strict mode"
# -e: Exit immediately if any command fails.
# -u: Treat unset variables as an error.
# -o pipefail: Ensures that a pipeline command fails if any part of it fails.
set -euo pipefail

# Fail loudly if any required connection variable is missing.
# These are the same DB_* names used by .env.example and edas.db.connection.get_engine().
# There are deliberately no defaults, so a missing credential is an explicit error.
: "${DB_HOST:?DB_HOST is not set}"
: "${DB_PORT:?DB_PORT is not set}"
: "${DB_USER:?DB_USER is not set}"
: "${DB_PASSWORD:?DB_PASSWORD is not set}"
: "${DB_NAME:?DB_NAME is not set}"

# Execute the psql command-line utility to run the schema file.
# The connection string is built dynamically using environment variables.
psql "host=${DB_HOST} port=${DB_PORT} user=${DB_USER} dbname=${DB_NAME} password=${DB_PASSWORD}" -f sql/01_schema.sql

# Print a success message to the console upon completion.
echo "DB initialized with your schema."