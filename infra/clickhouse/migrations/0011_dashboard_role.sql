-- Local read-only dashboard identity; the existing service password is supplied by migrate.sh.
CREATE ROLE IF NOT EXISTS sentinel_dashboard;
GRANT SELECT ON bronze.otel_traces TO sentinel_dashboard;
CREATE USER IF NOT EXISTS sentinel_dashboard_u IDENTIFIED WITH sha256_password BY {pw:String}
  SETTINGS readonly = 2;
GRANT sentinel_dashboard TO sentinel_dashboard_u;
