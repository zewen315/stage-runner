-- The default postgres image only creates the database named by
-- POSTGRES_DB (resource_store). workflow_service owns a separate
-- database on the same server -- each service's data stays its own,
-- nobody reaches into another service's tables directly.
CREATE DATABASE workflow_service;
