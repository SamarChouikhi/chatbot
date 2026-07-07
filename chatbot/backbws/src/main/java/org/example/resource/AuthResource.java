package org.example.resource;

import org.example.dto.AuthResponse;
import org.example.dto.LoginRequest;
import org.example.service.AuthService;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;
import jakarta.inject.Inject;
import jakarta.validation.Valid;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import org.jboss.logging.Logger;
import java.util.Map;

@Path("/api/auth")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class AuthResource {

    private static final Logger LOG = Logger.getLogger(AuthResource.class);

    @Inject
    AuthService authService;

    /** POST /api/auth/login */
    @POST
    @Path("/login")
    @PermitAll
    public Response login(@Valid LoginRequest request) {
        try {
            AuthResponse response = authService.login(request);
            return Response.ok(response).build();
        } catch (NotAuthorizedException e) {
            return Response.status(Response.Status.UNAUTHORIZED)
                    .entity(new ErrorMessage(e.getMessage()))
                    .build();
        } catch (Exception e) {
            LOG.error("Erreur login", e);
            return Response.status(Response.Status.INTERNAL_SERVER_ERROR)
                    .entity(new ErrorMessage("Erreur serveur"))
                    .build();
        }
    }

    /** POST /api/auth/refresh */
    @POST
    @Path("/refresh")
    @PermitAll
    public Response refresh(Map<String, String> body) {
        try {
            String refreshToken = body.get("refresh_token");
            if (refreshToken == null || refreshToken.isBlank()) {
                return Response.status(Response.Status.BAD_REQUEST)
                        .entity(new ErrorMessage("refresh_token manquant"))
                        .build();
            }
            AuthResponse response = authService.refresh(refreshToken);
            return Response.ok(response).build();
        } catch (NotAuthorizedException e) {
            return Response.status(Response.Status.UNAUTHORIZED)
                    .entity(new ErrorMessage(e.getMessage()))
                    .build();
        } catch (Exception e) {
            LOG.error("Erreur refresh", e);
            return Response.status(Response.Status.INTERNAL_SERVER_ERROR)
                    .entity(new ErrorMessage("Erreur serveur"))
                    .build();
        }
    }

    /** POST /api/auth/logout */
    @POST
    @Path("/logout")
    @RolesAllowed({"ADMIN", "ADVISOR", "USER"})
    public Response logout() {
        return Response.ok(new ErrorMessage("Déconnexion réussie")).build();
    }

    public static class ErrorMessage {
        public String message;
        public ErrorMessage(String message) { this.message = message; }
    }
}