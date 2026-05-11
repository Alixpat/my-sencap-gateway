-- ChirpStack v4 : création du rôle, de la base et des extensions Postgres.
-- Mot de passe par défaut = "chirpstack" (à changer en prod ; cohérent avec
-- le DSN par défaut de /etc/chirpstack/chirpstack.toml).
-- À exécuter en tant que postgres :
--   sudo -u postgres psql -v ON_ERROR_STOP=1 -f setup-db.sql

CREATE ROLE chirpstack WITH LOGIN PASSWORD 'chirpstack';
CREATE DATABASE chirpstack WITH OWNER chirpstack;

\connect chirpstack

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS hstore;
