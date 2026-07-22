BEGIN;

CREATE TABLE household_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    invited_by_user_id UUID NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT household_invitations_household_fk FOREIGN KEY (household_id) REFERENCES households (id),
    CONSTRAINT household_invitations_inviter_membership_fk
        FOREIGN KEY (household_id, invited_by_user_id)
        REFERENCES household_members (household_id, user_id),
    CONSTRAINT household_invitations_email_normalized CHECK (email = lower(btrim(email)) AND btrim(email) <> ''),
    CONSTRAINT household_invitations_role_valid CHECK (role IN ('admin', 'member')),
    CONSTRAINT household_invitations_token_hash_valid CHECK (token_hash ~ '^[0-9a-f]{64}$')
);

CREATE INDEX household_invitations_expires_at_idx ON household_invitations (expires_at);
CREATE UNIQUE INDEX household_invitations_pending_email_unique
    ON household_invitations (household_id, lower(email))
    WHERE accepted_at IS NULL;

COMMIT;
