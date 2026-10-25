package org.example.service;

import org.example.dto.AuthResponse;
import org.example.dto.LoginRequest;
import org.example.entity.UUser;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.transaction.Transactional;
import jakarta.ws.rs.NotAuthorizedException;
import org.jboss.logging.Logger;
import java.time.LocalDate;
import java.time.LocalDateTime;

@ApplicationScoped
public class AuthService {

    private static final Logger LOG = Logger.getLogger(AuthService.class);

    @Inject
    JwtService jwtService;

    /**
     * Le constructeur NotAuthorizedException(Object) interprète son argument comme un
     * challenge WWW-Authenticate : getMessage() renverrait alors "HTTP 401 Unauthorized".
     */
    private static NotAuthorizedException unauthorized(String message) {
        return new NotAuthorizedException(message, "Bearer");
    }

    @Transactional
    public AuthResponse login(LoginRequest request) {
        // 1. Chercher par login — trim : un espace collé/autocomplété ne doit pas rendre le compte introuvable
        String login = request.login == null ? "" : request.login.trim();
        UUser user = UUser.findByLogin(login).orElseThrow(() -> {
            LOG.warnf("Login échoué : utilisateur inconnu '%s'", login);
            return unauthorized("Login ou mot de passe incorrect");
        });

        // 2. Vérifier blocage
        if (user.isBlocked()) {
            throw unauthorized("Compte temporairement bloqué. Réessayez plus tard.");
        }

        // 3. Vérifier mot de passe
        if (!user.checkPassword(request.password)) {
            LOG.warnf("Login échoué : mot de passe incorrect pour '%s'", user.login);
            recordFailedAttempt(user.login);
            throw unauthorized("Login ou mot de passe incorrect");
        }

        // 4. Vérifier expiration — pwdExpDate est déjà LocalDate, pas besoin de .toLocalDate()
        if (user.pwdExpDate != null && user.pwdExpDate.isBefore(LocalDate.now())) {
            throw unauthorized("Mot de passe expiré");
        }

        // 5. Réinitialiser les tentatives en cas de succès
        user.resetFailedAttempts();

        // 6. Générer tokens
        String accessToken  = jwtService.generateAccessToken(user);
        String refreshToken = jwtService.generateRefreshToken(user);

        return buildResponse(user, accessToken, refreshToken);
    }

    @Inject
    io.smallrye.jwt.auth.principal.JWTParser jwtParser;

    public AuthResponse refresh(String refreshTokenStr) {
        try {
            org.eclipse.microprofile.jwt.JsonWebToken jwt = jwtParser.parse(refreshTokenStr);
            String type = jwt.getClaim("type");
            if (!"refresh".equals(type)) {
                throw unauthorized("Token invalide");
            }
            String login = jwt.getSubject();
            UUser user = UUser.findByLogin(login)
                    .orElseThrow(() -> unauthorized("Utilisateur introuvable"));
            if (user.isBlocked()) {
                throw unauthorized("Compte bloqué");
            }
            String newAccess  = jwtService.generateAccessToken(user);
            String newRefresh = jwtService.generateRefreshToken(user);
            return buildResponse(user, newAccess, newRefresh);
        } catch (NotAuthorizedException e) {
            throw e;
        } catch (Exception e) {
            LOG.error("Erreur refresh token", e);
            throw unauthorized("Refresh token invalide ou expiré");
        }
    }

    /** Transaction séparée pour que l'incrément survive au rollback du login. */
    @Transactional(Transactional.TxType.REQUIRES_NEW)
    public void recordFailedAttempt(String login) {
        UUser.findByLogin(login).ifPresent(u -> {
            u.incrementFailedAttempts();
            u.persist();
        });
    }

    /** Transaction séparée pour libérer le blocage expiré sans rollback. */
    @Transactional(Transactional.TxType.REQUIRES_NEW)
    public void clearExpiredBlock(String login) {
        UUser.findByLogin(login).ifPresent(u -> {
            if (u.blockedUntil != null && u.blockedUntil.isBefore(LocalDateTime.now())) {
                u.failedAttempts = 0;
                u.blockedUntil   = null;
                u.persist();
            }
        });
    }

    private AuthResponse buildResponse(UUser user, String accessToken, String refreshToken) {
        AuthResponse.UserInfo info = new AuthResponse.UserInfo();
        info.login       = user.login;
        info.role        = user.getRole();
        info.loginPere   = user.loginPere;
        info.userId      = user.login;
        info.permissions = (user.userRole != null && user.userRole.permissions != null)
            ? user.userRole.permissions.stream()
                .map(p -> p.permission)
                .sorted()
                .collect(java.util.stream.Collectors.toList())
            : java.util.List.of();
        return AuthResponse.of(accessToken, refreshToken, jwtService.getAccessTokenDuration(), info);
    }
}