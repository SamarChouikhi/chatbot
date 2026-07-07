-- Migration : ajout des colonnes pour la fonctionnalité "mot de passe oublié"
-- À exécuter UNE SEULE FOIS sur la base bw_samar avant de démarrer le backend.
USE bw_samar;

ALTER TABLE u_users
  ADD COLUMN IF NOT EXISTS phone             VARCHAR(20)  DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS reset_token       VARCHAR(64)  DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS reset_token_expiry DATETIME    DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS failed_attempts   INT          NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS blocked_until     DATETIME     DEFAULT NULL;
