\getenv app_password POSTGRES_APP_PASSWORD
\getenv database_name POSTGRES_DB

SELECT format(
    'CREATE ROLE medigest_policy_owner NOLOGIN NOSUPERUSER NOCREATEDB '
    'NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS'
) \gexec

SELECT format(
    'CREATE ROLE medigest_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
    'NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
    :'app_password'
) \gexec

SELECT format('REVOKE CONNECT, TEMP ON DATABASE %I FROM PUBLIC', :'database_name') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO medigest_app', :'database_name') \gexec
ALTER ROLE medigest_app SET row_security = on;
