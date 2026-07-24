BEGIN;

ALTER TABLE merchants
    ADD COLUMN address TEXT,
    ADD COLUMN normalized_address TEXT NOT NULL DEFAULT '';

ALTER TABLE merchants
    DROP CONSTRAINT merchants_normalized_name_unique,
    ADD CONSTRAINT merchants_identity_unique
        UNIQUE (household_id, normalized_name, normalized_address);

COMMIT;
