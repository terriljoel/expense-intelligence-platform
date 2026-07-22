BEGIN;

CREATE TABLE user_credentials (
    user_id UUID PRIMARY KEY,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT user_credentials_user_fk
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT user_credentials_password_hash_not_blank
        CHECK (btrim(password_hash) <> '')
);

CREATE TABLE auth_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL,
    user_id UUID NOT NULL,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT auth_sessions_membership_fk
        FOREIGN KEY (household_id, user_id)
        REFERENCES household_members (household_id, user_id)
        ON DELETE CASCADE,
    CONSTRAINT auth_sessions_token_hash_valid
        CHECK (token_hash ~ '^[0-9a-f]{64}$')
);

CREATE INDEX auth_sessions_expires_at_idx
    ON auth_sessions (expires_at);

COMMIT;
