BEGIN;

CREATE UNIQUE INDEX payment_methods_active_identity_unique
    ON payment_methods (
        household_id,
        user_id,
        lower(btrim(name)),
        method_type,
        lower(btrim(COALESCE(provider, ''))),
        COALESCE(last_four, '')
    )
    WHERE is_active;

COMMIT;
