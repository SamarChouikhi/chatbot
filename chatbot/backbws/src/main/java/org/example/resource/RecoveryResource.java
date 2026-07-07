package org.example.resource;

import jakarta.inject.Inject;
import jakarta.ws.rs.*;
import org.jboss.logging.Logger;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import org.example.service.RecoveryService;

@Path("/recovery")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class RecoveryResource {

    private static final Logger LOG = Logger.getLogger(RecoveryResource.class);

    @Inject
    RecoveryService recoveryService;

    /**
     * Étape 1 — Demande de récupération
     */
    @POST
    @Path("/request")
    public Response request(RequestBody body) {
        if (body == null || body.email == null || body.email.isBlank()) {
            return Response.status(Response.Status.BAD_REQUEST)
                    .entity(new MessageResponse("Email requis.")).build();
        }
        try {
            recoveryService.requestRecovery(body.email);
            return Response.ok(new MessageResponse("Si votre email est valide, vous recevrez deux codes.")).build();
        } catch (IllegalStateException e) {
            return Response.status(429)
                    .entity(new MessageResponse(e.getMessage())).build();
        } catch (Exception e) {
            LOG.error("Erreur demande récupération", e);
            return Response.status(Response.Status.INTERNAL_SERVER_ERROR)
                    .entity(new MessageResponse("Erreur interne du serveur")).build();
        }
    }

    /**
     * Étape 2 — Vérification du code reçu par email
     */
    @POST
    @Path("/verify")
    public Response verify(VerifyRequest request) {
        if (request == null || request.email == null || request.code == null) {
            return Response.status(Response.Status.BAD_REQUEST)
                    .entity(new MessageResponse("Email et code requis.")).build();
        }
        try {
            String resetToken = recoveryService.verifyCode(request.email, request.code);
            return Response.ok(new ResetTokenResponse(resetToken)).build();
        } catch (IllegalStateException e) {
            return Response.status(429)
                    .entity(new MessageResponse(e.getMessage())).build();
        } catch (IllegalArgumentException e) {
            return Response.status(Response.Status.BAD_REQUEST)
                    .entity(new MessageResponse(e.getMessage())).build();
        } catch (Exception e) {
            LOG.error("Erreur vérification code", e);
            return Response.status(Response.Status.INTERNAL_SERVER_ERROR)
                    .entity(new MessageResponse("Erreur interne du serveur")).build();
        }
    }

    /**
     * Étape 3 — Réinitialisation du mot de passe
     */
    @POST
    @Path("/reset")
    public Response reset(ResetRequest request) {
        if (request == null || request.resetToken == null || request.newPassword == null) {
            return Response.status(Response.Status.BAD_REQUEST)
                    .entity(new MessageResponse("Token et nouveau mot de passe requis.")).build();
        }
        try {
            recoveryService.resetPassword(request.resetToken, request.newPassword);
            return Response.ok(new MessageResponse("Mot de passe réinitialisé avec succès.")).build();
        } catch (IllegalArgumentException e) {
            return Response.status(Response.Status.BAD_REQUEST)
                    .entity(new MessageResponse(e.getMessage())).build();
        } catch (Exception e) {
            LOG.error("Erreur réinitialisation mot de passe", e);
            return Response.status(Response.Status.INTERNAL_SERVER_ERROR)
                    .entity(new MessageResponse("Erreur interne du serveur")).build();
        }
    }

    // ─── DTOs ───────────────────────────────────────────────────────────────────

    public static class RequestBody {
        public String email;
    }

    public static class VerifyRequest {
        public String email;
        public String code;
    }

    public static class ResetTokenResponse {
        public String resetToken;
        public ResetTokenResponse(String resetToken) { this.resetToken = resetToken; }
    }

    public static class ResetRequest {
        public String resetToken;
        public String newPassword;
    }

    // ✅ Nouveau DTO — toutes les réponses texte passent par ici
    public static class MessageResponse {
        public String message;
        public MessageResponse(String message) { this.message = message; }
    }
}