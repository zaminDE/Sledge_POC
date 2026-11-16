DROP VIEW IF EXISTS sledge_analytics.bill_cycle_time_weekly, sledge_analytics.bill_lifecycle,
                    sledge_analytics.documents, sledge_analytics.weekly_active_companies;
DROP TABLE IF EXISTS sledge_ga4.outbox, sledge_core.fact_event, sledge_core.dim_tenant, sledge_raw.events,
                     sledge_core.ref_action, sledge_core.ref_module, sledge_core.ref_surface,
                     sledge_core.ref_channel, sledge_core.ref_actor_type;
DROP FUNCTION IF EXISTS sledge_core.week_start;
DROP SCHEMA IF EXISTS sledge_ga4;
DROP SCHEMA IF EXISTS sledge_analytics;
DROP SCHEMA IF EXISTS sledge_core;
DROP SCHEMA IF EXISTS sledge_raw;
GO
CREATE SCHEMA sledge_raw;
GO
CREATE SCHEMA sledge_core;
GO
CREATE SCHEMA sledge_analytics;
GO
CREATE SCHEMA sledge_ga4;
GO

CREATE TABLE sledge_raw.events (
    event_id      uniqueidentifier NOT NULL CONSTRAINT pk_raw_events PRIMARY KEY,
    received_at   datetime2(0)     NOT NULL CONSTRAINT df_raw_events_received DEFAULT SYSUTCDATETIME(),
    payload       nvarchar(max)    NOT NULL CONSTRAINT ck_raw_events_json CHECK (ISJSON(payload) = 1),
    status        varchar(8)       NOT NULL CONSTRAINT ck_raw_events_status CHECK (status IN ('accepted', 'rejected')),
    reject_reason varchar(200)     NULL,
    CONSTRAINT ck_raw_events_reason CHECK ((status = 'rejected' AND reject_reason IS NOT NULL)
                                        OR (status = 'accepted' AND reject_reason IS NULL))
);

CREATE TABLE sledge_core.ref_action     (code varchar(16) COLLATE Latin1_General_BIN2 NOT NULL CONSTRAINT pk_ref_action PRIMARY KEY);
CREATE TABLE sledge_core.ref_module     (code varchar(16) COLLATE Latin1_General_BIN2 NOT NULL CONSTRAINT pk_ref_module PRIMARY KEY);
CREATE TABLE sledge_core.ref_surface    (code varchar(16) COLLATE Latin1_General_BIN2 NOT NULL CONSTRAINT pk_ref_surface PRIMARY KEY);
CREATE TABLE sledge_core.ref_channel    (code varchar(16) COLLATE Latin1_General_BIN2 NOT NULL CONSTRAINT pk_ref_channel PRIMARY KEY);
CREATE TABLE sledge_core.ref_actor_type (code varchar(16) COLLATE Latin1_General_BIN2 NOT NULL CONSTRAINT pk_ref_actor_type PRIMARY KEY);

INSERT INTO sledge_core.ref_action (code) VALUES
    ('created'), ('received'), ('uploaded'), ('requested'), ('sent'),
    ('submitted'), ('approved'), ('signed'), ('verified'), ('paid');
INSERT INTO sledge_core.ref_module (code) VALUES
    ('bills'), ('invoices'), ('contracts'), ('lien_waivers'), ('cois'), ('change_orders'), ('pay_packages');
INSERT INTO sledge_core.ref_surface (code) VALUES
    ('web_app'), ('mobile_app'), ('portal'), ('background');
INSERT INTO sledge_core.ref_channel (code) VALUES
    ('direct'), ('upload'), ('mobile_scan'), ('email'), ('e_signature'), ('ach'), ('card'), ('check'), ('integration');
INSERT INTO sledge_core.ref_actor_type (code) VALUES
    ('user'), ('agent'), ('external');

CREATE TABLE sledge_core.dim_tenant (
    tenant_id     varchar(32)   NOT NULL CONSTRAINT pk_dim_tenant PRIMARY KEY,
    company_name  nvarchar(200) NOT NULL,
    tax_id        varchar(20)   NULL,
    first_seen_at datetime2(0)  NOT NULL
);

CREATE TABLE sledge_core.fact_event (
    event_id          uniqueidentifier NOT NULL CONSTRAINT pk_fact_event PRIMARY KEY
                      CONSTRAINT fk_fact_event_raw REFERENCES sledge_raw.events (event_id),
    occurred_at       datetime2(0)  NOT NULL,
    tenant_id         varchar(32)   NOT NULL CONSTRAINT fk_fact_event_tenant REFERENCES sledge_core.dim_tenant (tenant_id),
    user_id           varchar(32)   NULL,
    actor_type        varchar(16) COLLATE Latin1_General_BIN2 NOT NULL
                      CONSTRAINT fk_fact_event_actor REFERENCES sledge_core.ref_actor_type (code),
    event_name        varchar(64)   NOT NULL,
    action            varchar(16) COLLATE Latin1_General_BIN2 NOT NULL
                      CONSTRAINT fk_fact_event_action REFERENCES sledge_core.ref_action (code),
    module            varchar(16) COLLATE Latin1_General_BIN2 NOT NULL
                      CONSTRAINT fk_fact_event_module REFERENCES sledge_core.ref_module (code),
    surface           varchar(16) COLLATE Latin1_General_BIN2 NOT NULL
                      CONSTRAINT fk_fact_event_surface REFERENCES sledge_core.ref_surface (code),
    channel           varchar(16) COLLATE Latin1_General_BIN2 NOT NULL
                      CONSTRAINT fk_fact_event_channel REFERENCES sledge_core.ref_channel (code),
    document_id       varchar(32)   NOT NULL,
    amount_cents      bigint        NULL,
    counterparty_name nvarchar(200) NULL,
    processing_ms     int           NULL
);
CREATE INDEX ix_fact_event_time   ON sledge_core.fact_event (occurred_at);
CREATE INDEX ix_fact_event_tenant ON sledge_core.fact_event (tenant_id, occurred_at);
CREATE INDEX ix_fact_event_doc    ON sledge_core.fact_event (tenant_id, module, document_id);
GO

CREATE FUNCTION sledge_core.week_start (@at datetime2(0))
RETURNS date
WITH SCHEMABINDING
AS
BEGIN
    RETURN DATEADD(day, -(DATEDIFF(day, CONVERT(date, '19000101', 112), @at) % 7), CAST(@at AS date));
END;
GO

CREATE VIEW sledge_analytics.weekly_active_companies AS
SELECT sledge_core.week_start(occurred_at) AS week_start,
       COUNT(DISTINCT tenant_id)           AS active_companies
FROM sledge_core.fact_event
WHERE actor_type = 'user'
GROUP BY sledge_core.week_start(occurred_at);
GO

CREATE VIEW sledge_analytics.documents AS
SELECT tenant_id, module, document_id,
       MIN(occurred_at)                         AS first_seen_at,
       sledge_core.week_start(MIN(occurred_at)) AS week_start
FROM sledge_core.fact_event
GROUP BY tenant_id, module, document_id;
GO

CREATE VIEW sledge_analytics.bill_lifecycle AS
SELECT tenant_id,
       document_id AS bill_id,
       MIN(CASE WHEN action = 'received' THEN occurred_at END) AS received_at,
       MIN(CASE WHEN action = 'approved' THEN occurred_at END) AS approved_at,
       MIN(CASE WHEN action = 'paid'     THEN occurred_at END) AS paid_at,
       MAX(amount_cents)                                       AS amount_cents
FROM sledge_core.fact_event
WHERE module = 'bills'
GROUP BY tenant_id, document_id;
GO

CREATE VIEW sledge_analytics.bill_cycle_time_weekly AS
WITH paid AS (
    SELECT sledge_core.week_start(paid_at)                       AS week_start,
           DATEDIFF_BIG(second, received_at, paid_at) / 86400.0  AS days
    FROM sledge_analytics.bill_lifecycle
    WHERE paid_at IS NOT NULL AND received_at IS NOT NULL
), ranked AS (
    SELECT week_start, days,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days) OVER (PARTITION BY week_start) AS median_days
    FROM paid
)
SELECT week_start,
       COUNT(*)                                    AS bills_paid,
       CAST(ROUND(AVG(days), 2) AS decimal(9, 2))        AS avg_days,
       CAST(ROUND(MAX(median_days), 2) AS decimal(9, 2)) AS median_days
FROM ranked
GROUP BY week_start;
GO

CREATE TABLE sledge_ga4.outbox (
    outbox_id       bigint IDENTITY(1, 1) NOT NULL CONSTRAINT pk_outbox PRIMARY KEY,
    source_event_id uniqueidentifier NOT NULL CONSTRAINT uq_outbox_source UNIQUE
                    CONSTRAINT fk_outbox_event REFERENCES sledge_core.fact_event (event_id),
    action          varchar(16) COLLATE Latin1_General_BIN2 NOT NULL
                    CONSTRAINT fk_outbox_action REFERENCES sledge_core.ref_action (code),
    module          varchar(16) COLLATE Latin1_General_BIN2 NOT NULL
                    CONSTRAINT fk_outbox_module REFERENCES sledge_core.ref_module (code),
    surface         varchar(16) COLLATE Latin1_General_BIN2 NOT NULL
                    CONSTRAINT fk_outbox_surface REFERENCES sledge_core.ref_surface (code),
    channel         varchar(16) COLLATE Latin1_General_BIN2 NOT NULL
                    CONSTRAINT fk_outbox_channel REFERENCES sledge_core.ref_channel (code),
    tenant_hash     varchar(32) COLLATE Latin1_General_BIN2 NOT NULL
                    CONSTRAINT ck_outbox_tenant_hash
                    CHECK (DATALENGTH(tenant_hash) = 32 AND tenant_hash + '|' NOT LIKE '%[^0-9a-f]%|'),
    exported_at     datetime2(0) NULL
);
GO
