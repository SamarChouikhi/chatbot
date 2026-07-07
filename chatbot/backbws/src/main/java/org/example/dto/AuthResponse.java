package org.example.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class AuthResponse {

    @JsonProperty("access_token")
    public String accessToken;

    @JsonProperty("refresh_token")
    public String refreshToken;

    @JsonProperty("token_type")
    public String tokenType = "bearer";

    @JsonProperty("expires_in")
    public long expiresIn;

    public UserInfo user;

    public static class UserInfo {
        public String login;
        public String role;
        public String loginPere;
        public String userId;  // = login, utilisé par le chatbot
        public java.util.List<String> permissions;
    }

    public static AuthResponse of(String accessToken, String refreshToken, long expiresIn, UserInfo user) {
        AuthResponse r = new AuthResponse();
        r.accessToken = accessToken;
        r.refreshToken = refreshToken;
        r.expiresIn = expiresIn;
        r.user = user;
        return r;
    }
}