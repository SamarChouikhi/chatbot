package org.example.service;

import io.quarkus.mailer.Mail;
import io.quarkus.mailer.Mailer;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.transaction.Transactional;
import org.apache.commons.codec.digest.DigestUtils;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.example.entity.UUser;
import org.jboss.logging.Logger;
import org.mindrot.jbcrypt.BCrypt;

import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.Base64;

@ApplicationScoped
public class RecoveryService {

    private static final Logger LOG = Logger.getLogger(RecoveryService.class);

    @Inject
    Mailer mailer;

    @ConfigProperty(name = "recovery.token.length", defaultValue = "6")
    int tokenLength;

    @ConfigProperty(name = "recovery.token.expiry.minutes", defaultValue = "10")
    int expiryMinutes;

    @ConfigProperty(name = "recovery.max.attempts", defaultValue = "3")
    int maxAttempts;

    @ConfigProperty(name = "recovery.block.minutes", defaultValue = "15")
    int blockMinutes;

    /**
     * Étape 1 : Générer et envoyer le code de récupération.
     * L'exception mailer est capturée en interne pour ne pas rollback la transaction :
     * le token est déjà persisté — en mode mock, Quarkus logue le code dans la console.
     */
    @Transactional
    public void requestRecovery(String email) {
        UUser user = UUser.findByLogin(email).orElse(null);
        if (user == null) return; // réponse neutre — ne pas révéler si l'email existe

        if (user.isBlocked()) {
            throw new IllegalStateException("Trop de tentatives. Réessayez plus tard.");
        }

        user.failedAttempts = 0;
        user.blockedUntil   = null;

        String code = generateSecureToken(tokenLength);
        user.resetToken       = hashToken(code);
        user.resetTokenExpiry = LocalDateTime.now().plusMinutes(expiryMinutes);
        user.persist();

        try {
            mailer.send(Mail.withText(
                    email,
                    "Récupération de mot de passe",
                    "Votre code de récupération : " + code + "\n\n" +
                            "Ce code expire dans " + expiryMinutes + " minutes.\n" +
                            "Si vous n'avez pas fait cette demande, ignorez cet email."
            ));
        } catch (Exception e) {
            // Ne pas rethrow : la transaction commit normalement, le token est sauvé.
            // En prod, configurer MAILER_PASSWORD avec un App Password Gmail.
            LOG.warnf("Envoi email échoué pour %s : %s", email, e.getMessage());
        }
    }

    /**
     * Étape 2 : Vérifier le code reçu par email
     * Retourne un resetToken final pour l'étape 3
     */
    @Transactional
    public String verifyCode(String email, String code) {
        UUser user = UUser.findByLogin(email).orElse(null);
        if (user == null) {
            throw new IllegalArgumentException("Email invalide.");
        }

        if (user.isBlocked()) {
            throw new IllegalStateException("Trop de tentatives. Réessayez dans 15 minutes.");
        }

        if (user.resetToken == null || user.resetTokenExpiry == null) {
            throw new IllegalArgumentException("Aucune demande de récupération en cours. Refaites une demande.");
        }

        if (user.resetTokenExpiry.isBefore(LocalDateTime.now())) {
            // Expiration naturelle → pas de pénalité, juste informer
            user.resetToken = null;
            user.resetTokenExpiry = null;
            user.persist();
            throw new IllegalArgumentException("Code expiré. Veuillez refaire une demande.");
        }

        // Vérifier le code soumis (comparaison des hashes)
        if (!user.resetToken.equals(hashToken(code))) {
            // Mauvais code → on pénalise
            user.incrementFailedAttempts();
            user.persist();
            int remaining = maxAttempts - user.failedAttempts;
            if (remaining > 0) {
                throw new IllegalArgumentException("Code invalide. " + remaining + " tentative(s) restante(s).");
            } else {
                throw new IllegalStateException("Compte bloqué pendant " + blockMinutes + " minutes.");
            }
        }

        // Succès — reset compteur et génération du token final de réinitialisation
        user.resetFailedAttempts();
        String resetToken = generateSecureToken(32);
        user.resetToken = hashToken(resetToken);
        user.resetTokenExpiry = LocalDateTime.now().plusMinutes(30); // 30 min pour reset
        user.persist();

        return resetToken;
    }

    /**
     * Étape 3 : Réinitialiser le mot de passe avec le resetToken final
     */
    @Transactional
    public void resetPassword(String resetToken, String newPassword) {
        UUser user = UUser.findByResetToken(hashToken(resetToken)).orElse(null);
        if (user == null) {
            throw new IllegalArgumentException("Token de réinitialisation invalide ou expiré.");
        }

        // Validation basique du mot de passe
        if (newPassword == null || newPassword.length() < 8) {
            throw new IllegalArgumentException("Le mot de passe doit contenir au moins 8 caractères.");
        }

        user.pwd = hashPassword(newPassword); // bcrypt
        user.resetToken = null;
        user.resetTokenExpiry = null;
        user.failedAttempts = 0;
        user.blockedUntil = null;
        user.persist();
    }

    // ─── Utilitaires ────────────────────────────────────────────────────────────

    private String generateSecureToken(int length) {
        byte[] bytes = new byte[length + 4]; // buffer pour éviter tronquage base64
        new SecureRandom().nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes)
                .substring(0, length);
    }

    private String hashToken(String token) {
        return DigestUtils.sha256Hex(token);
    }

    private String hashPassword(String password) {
        return BCrypt.hashpw(password, BCrypt.gensalt(12));
    }
}