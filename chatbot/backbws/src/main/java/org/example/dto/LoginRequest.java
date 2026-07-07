package org.example.dto;

import jakarta.validation.constraints.NotBlank;

public class LoginRequest {

    @NotBlank(message = "Le login est obligatoire")
    public String login;

    @NotBlank(message = "Le mot de passe est obligatoire")
    public String password;
}