package org.example.service;

import org.example.entity.UUser;
import io.smallrye.jwt.build.Jwt;
import jakarta.enterprise.context.ApplicationScoped;
import org.eclipse.microprofile.config.inject.ConfigProperty;

import java.time.Duration;
import java.util.Set;

@ApplicationScoped
public class JwtService {

    @ConfigProperty(name = "ioit.jwt.duration", defaultValue = "3600")
    long jwtDuration;

    @ConfigProperty(name = "ioit.jwt.refresh-duration", defaultValue = "604800")
    long refreshDuration;

    @ConfigProperty(name = "ioit.jwt.issuer")
    String issuer;

    public String generateAccessToken(UUser user) {
        Set<String> groups = new java.util.HashSet<>();
        groups.add(user.getRole());
        if (user.userRole != null && user.userRole.permissions != null) {
            user.userRole.permissions.forEach(p -> groups.add(p.permission));
        }
        return Jwt.issuer(issuer)
                .subject(user.login)
                .groups(groups)
                .claim("login", user.login)
                .claim("role", user.getRole())
                .claim("userId", user.login)
                .claim("loginPere", user.loginPere != null ? user.loginPere : "")
                .claim("type", "access")
                .expiresIn(Duration.ofSeconds(jwtDuration))
                .sign();
    }

    public String generateRefreshToken(UUser user) {
        return Jwt.issuer(issuer)
                .subject(user.login)
                .claim("type", "refresh")
                .expiresIn(Duration.ofSeconds(refreshDuration))
                .sign();
    }

    public long getAccessTokenDuration() {
        return jwtDuration;
    }
}