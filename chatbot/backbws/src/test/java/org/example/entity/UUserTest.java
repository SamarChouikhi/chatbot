package org.example.entity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.mindrot.jbcrypt.BCrypt;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.HashSet;
import java.util.Set;

import static org.assertj.core.api.Assertions.*;

/**
 * Tests unitaires purs — UUser.
 * Aucun @QuarkusTest ni base de données : la classe est instanciée directement.
 */
class UUserTest {

    private UUser user;

    @BeforeEach
    void setUp() {
        user = new UUser();
        user.login = "alice";
        user.failedAttempts = 0;
    }

    // ── checkPassword ──────────────────────────────────────────────────────────

    @Nested
    @DisplayName("checkPassword()")
    class CheckPassword {

        @Test
        @DisplayName("BCrypt hash valide → true")
        void bcryptMatch() {
            user.pwd = BCrypt.hashpw("secret123", BCrypt.gensalt(4));
            assertThat(user.checkPassword("secret123")).isTrue();
        }

        @Test
        @DisplayName("BCrypt hash invalide → false")
        void bcryptNoMatch() {
            user.pwd = BCrypt.hashpw("secret123", BCrypt.gensalt(4));
            assertThat(user.checkPassword("wrong")).isFalse();
        }

        @Test
        @DisplayName("MD5 hash (ancien format) → true")
        void md5Match() {
            // MD5("admin") = 21232f297a57a5a743894a0e4a801fc3
            user.pwd = "21232f297a57a5a743894a0e4a801fc3";
            assertThat(user.checkPassword("admin")).isTrue();
        }

        @Test
        @DisplayName("MD5 hash invalide → false")
        void md5NoMatch() {
            user.pwd = "21232f297a57a5a743894a0e4a801fc3";
            assertThat(user.checkPassword("wrongpassword")).isFalse();
        }

        @Test
        @DisplayName("pwd null → false")
        void nullPwd() {
            user.pwd = null;
            assertThat(user.checkPassword("anything")).isFalse();
        }

        @Test
        @DisplayName("hash non-BCrypt non-MD5 ne lève pas d'exception (retourne false)")
        void unknownHashFormat() {
            user.pwd = "sha256:abcdef1234567890";
            // ni BCrypt ni MD5 → passe dans la branche MD5 → ne correspond pas
            assertThat(user.checkPassword("pass")).isFalse();
        }
    }

    // ── getRole ────────────────────────────────────────────────────────────────

    @Nested
    @DisplayName("getRole()")
    class GetRole {

        @Test
        @DisplayName("userRole défini avec nom → retourne le nom du rôle")
        void withUserRole() {
            UserRole role = new UserRole();
            role.userName = "ADMIN";
            user.userRole = role;
            assertThat(user.getRole()).isEqualTo("ADMIN");
        }

        @Test
        @DisplayName("pas de userRole et pas de loginPere → SUPER_ADMIN")
        void noUserRoleNoLoginPere() {
            user.userRole  = null;
            user.loginPere = null;
            assertThat(user.getRole()).isEqualTo("SUPER_ADMIN");
        }

        @Test
        @DisplayName("pas de userRole mais loginPere vide → SUPER_ADMIN")
        void noUserRoleEmptyLoginPere() {
            user.userRole  = null;
            user.loginPere = "  ";
            assertThat(user.getRole()).isEqualTo("SUPER_ADMIN");
        }

        @Test
        @DisplayName("pas de userRole mais loginPere renseigné → EMPLOYEE")
        void noUserRoleWithLoginPere() {
            user.userRole  = null;
            user.loginPere = "boss";
            assertThat(user.getRole()).isEqualTo("EMPLOYEE");
        }

        @Test
        @DisplayName("userRole avec userName null → SUPER_ADMIN (loginPere null)")
        void userRoleWithNullName() {
            UserRole role = new UserRole();
            role.userName  = null;
            user.userRole  = role;
            user.loginPere = null;
            assertThat(user.getRole()).isEqualTo("SUPER_ADMIN");
        }
    }

    // ── isBlocked ──────────────────────────────────────────────────────────────

    @Nested
    @DisplayName("isBlocked()")
    class IsBlocked {

        @Test
        @DisplayName("blockedUntil null → pas bloqué")
        void notBlockedWhenNull() {
            user.blockedUntil = null;
            assertThat(user.isBlocked()).isFalse();
        }

        @Test
        @DisplayName("blockedUntil dans le futur → bloqué")
        void blockedInFuture() {
            user.blockedUntil = LocalDateTime.now().plusMinutes(10);
            assertThat(user.isBlocked()).isTrue();
        }

        @Test
        @DisplayName("blockedUntil dans le passé → auto-reset et false")
        void unblockWhenPast() {
            user.failedAttempts = 5;
            user.blockedUntil   = LocalDateTime.now().minusMinutes(1);
            assertThat(user.isBlocked()).isFalse();
            assertThat(user.failedAttempts).isZero();
            assertThat(user.blockedUntil).isNull();
        }
    }

    // ── incrementFailedAttempts ────────────────────────────────────────────────

    @Nested
    @DisplayName("incrementFailedAttempts()")
    class IncrementFailedAttempts {

        @Test
        @DisplayName("1ère tentative → failedAttempts = 1, pas de blocage")
        void firstFailure() {
            user.failedAttempts = 0;
            user.incrementFailedAttempts();
            assertThat(user.failedAttempts).isEqualTo(1);
            assertThat(user.blockedUntil).isNull();
        }

        @Test
        @DisplayName("2ème tentative → failedAttempts = 2, pas de blocage")
        void secondFailure() {
            user.failedAttempts = 1;
            user.incrementFailedAttempts();
            assertThat(user.failedAttempts).isEqualTo(2);
            assertThat(user.blockedUntil).isNull();
        }

        @Test
        @DisplayName("3ème tentative → blocage pendant 15 minutes")
        void thirdFailureTriggerBlock() {
            user.failedAttempts = 2;
            user.incrementFailedAttempts();
            assertThat(user.failedAttempts).isEqualTo(3);
            assertThat(user.blockedUntil).isNotNull();
            assertThat(user.blockedUntil).isAfter(LocalDateTime.now().plusMinutes(14));
            assertThat(user.blockedUntil).isBefore(LocalDateTime.now().plusMinutes(16));
        }

        @Test
        @DisplayName("failedAttempts null → géré (initialise à 0 avant incrément)")
        void nullFailedAttempts() {
            user.failedAttempts = null;
            user.incrementFailedAttempts();
            assertThat(user.failedAttempts).isEqualTo(1);
        }
    }

    // ── resetFailedAttempts ───────────────────────────────────────────────────

    @Nested
    @DisplayName("resetFailedAttempts()")
    class ResetFailedAttempts {

        @Test
        @DisplayName("réinitialise compteur et blockedUntil")
        void resetsAll() {
            user.failedAttempts = 5;
            user.blockedUntil   = LocalDateTime.now().plusHours(1);
            user.resetFailedAttempts();
            assertThat(user.failedAttempts).isZero();
            assertThat(user.blockedUntil).isNull();
        }
    }

    // ── hasPermission ──────────────────────────────────────────────────────────

    @Nested
    @DisplayName("hasPermission()")
    class HasPermission {

        @Test
        @DisplayName("userRole null → false")
        void nullRole() {
            user.userRole = null;
            assertThat(user.hasPermission("VIEW_ALERTS")).isFalse();
        }

        @Test
        @DisplayName("permissions null → false")
        void nullPermissions() {
            UserRole role    = new UserRole();
            role.permissions = null;
            user.userRole    = role;
            assertThat(user.hasPermission("VIEW_ALERTS")).isFalse();
        }

        @Test
        @DisplayName("permission présente → true")
        void permissionFound() {
            Permission perm    = new Permission();
            perm.permission    = "VIEW_ALERTS";
            Set<Permission> ps = new HashSet<>();
            ps.add(perm);
            UserRole role    = new UserRole();
            role.permissions = ps;
            user.userRole    = role;
            assertThat(user.hasPermission("VIEW_ALERTS")).isTrue();
        }

        @Test
        @DisplayName("permission absente → false")
        void permissionNotFound() {
            Permission perm    = new Permission();
            perm.permission    = "VIEW_ALERTS";
            Set<Permission> ps = new HashSet<>();
            ps.add(perm);
            UserRole role    = new UserRole();
            role.permissions = ps;
            user.userRole    = role;
            assertThat(user.hasPermission("DELETE_USERS")).isFalse();
        }

        @Test
        @DisplayName("permissions vide → false")
        void emptyPermissions() {
            UserRole role    = new UserRole();
            role.permissions = new HashSet<>();
            user.userRole    = role;
            assertThat(user.hasPermission("ANYTHING")).isFalse();
        }
    }
}
