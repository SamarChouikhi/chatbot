
        package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import org.mindrot.jbcrypt.BCrypt;
import java.time.LocalDateTime;
import java.util.Optional;
import java.time.LocalDate;

@Entity
@Table(name = "u_users", schema = "bw_samar")
public class UUser extends PanacheEntityBase {

    @Id
    @Column(name = "login", length = 45)
    public String login;

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "role_id", referencedColumnName = "id")
    public UserRole userRole;

    @Column(name = "pwd", length = 255)   // agrandi pour bcrypt
    public String pwd;

    @Column(name = "login_pere", length = 45)
    public String loginPere;

    @Column(name = "pwd_exp_date")
    public LocalDate pwdExpDate;

    @Column(name = "GMT_PLUS")
    public Integer gmtPlus;

    @Column(name = "is_advisor")
    public Integer isAdvisor;

    @Column(name = "login_fb", length = 45)
    public String loginFb;

    @Column(name = "id_fb", length = 45)
    public String idFb;

    @Column(name = "id_fb_msg", length = 45)
    public String idFbMsg;

    // Nouveaux champs pour le forget password
    @Column(name = "phone", length = 20)
    public String phone;                      // numéro de téléphone (format international)

    @Column(name = "reset_token", length = 64)
    public String resetToken;                 // hash SHA-256 du token complet

    @Column(name = "reset_token_expiry")
    public LocalDateTime resetTokenExpiry;    // expiration du token

    @Column(name = "failed_attempts")
    public Integer failedAttempts = 0;        // compteur de tentatives échouées

    @Column(name = "blocked_until")
    public LocalDateTime blockedUntil;        // date de fin de blocage

    // ─── Finders ────────────────────────────────────────────────
    public static Optional<UUser> findByLogin(String login) {
        return find("login", login).firstResultOptional();
    }

    public static Optional<UUser> findByResetToken(String hashedToken) {
        return find("resetToken = ?1 AND resetTokenExpiry > ?2",
                hashedToken, LocalDateTime.now()).firstResultOptional();
    }

    // ─── Méthodes d'authentification ────────────────────────────
    public boolean checkPassword(String rawPassword) {
        if (this.pwd == null) return false;

        // BCrypt
        if (this.pwd.startsWith("$2a$") || this.pwd.startsWith("$2b$")) {
            return BCrypt.checkpw(rawPassword, this.pwd);
        }

        // MD5 (anciens utilisateurs en base)
        return this.pwd.equalsIgnoreCase(md5(rawPassword));
    }

    private String md5(String input) {
        try {
            java.security.MessageDigest md = java.security.MessageDigest.getInstance("MD5");
            byte[] hash = md.digest(input.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : hash) sb.append(String.format("%02x", b));
            return sb.toString();
        } catch (Exception e) {
            throw new RuntimeException("Erreur MD5", e);
        }
    }

    public String getRole() {
        if (userRole != null && userRole.userName != null) return userRole.userName;
        if (loginPere == null || loginPere.trim().isEmpty()) return "SUPER_ADMIN";
        return "EMPLOYEE";
    }

    public boolean hasPermission(String permissionName) {
        if (userRole == null || userRole.permissions == null) return false;
        return userRole.permissions.stream()
            .anyMatch(p -> permissionName.equals(p.permission));
    }

    // ─── Gestion du blocage ─────────────────────────────────────
    public boolean isBlocked() {
        if (blockedUntil == null) return false;
        // Blocage expiré : ne pas modifier l'état ici (risque rollback) — laisser AuthService.clearExpiredBlock()
        return blockedUntil.isAfter(LocalDateTime.now());
    }

    public void incrementFailedAttempts() {
        if (this.failedAttempts == null) this.failedAttempts = 0;
        this.failedAttempts++;
        if (this.failedAttempts >= 3) {
            this.blockedUntil = LocalDateTime.now().plusMinutes(15);
        }
    }

    public void resetFailedAttempts() {
        this.failedAttempts = 0;
        this.blockedUntil = null;
    }
}