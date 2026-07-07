package org.example.resource;

import io.quarkus.security.Authenticated;
import jakarta.annotation.security.RolesAllowed;
import jakarta.inject.Inject;
import jakarta.ws.rs.*;
import org.jboss.logging.Logger;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import org.eclipse.microprofile.jwt.JsonWebToken;
import org.example.dto.ChatRequest;
import org.example.dto.ChatResponse;
import org.example.service.AriaService;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

@Path("/api/chat")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class ChatRessource {

    private static final Logger LOG = Logger.getLogger(ChatRessource.class);

    @Inject AriaService  ariaService;
    @Inject JsonWebToken jwt;

    @POST
    @RolesAllowed({"USE_CHATBOT"})
    public Response chat(ChatRequest request) {
        try {
            if (request.question == null || request.question.isBlank())
                return Response.status(400).entity("{\"error\":\"Question vide\"}").build();

            request.user_id         = jwt.getClaim("userId");
            request.allowed_modules = mapGroupsToModules(jwt.getGroups());

            ChatResponse response = ariaService.ask(request);
            return Response.ok(response).build();
        } catch (Exception e) {
            LOG.error("Erreur interne", e);
            return Response.status(500)
                    .entity("{\"error\":\"Erreur interne du serveur\"}")
                    .build();
        }
    }

    @POST
    @Path("/new")
    @Authenticated
    public Response newThread() {
        try {
            return Response.ok(ariaService.newThread()).build();
        } catch (Exception e) {
            LOG.error("Erreur interne", e);
            return Response.status(500)
                    .entity("{\"error\":\"Erreur interne du serveur\"}")
                    .build();
        }
    }

    @GET
    @Path("/threads")
    @Authenticated
    public Response threads(@QueryParam("user_id") @DefaultValue("") String userId) {
        try {
            String uid = jwt.getClaim("userId");
            return Response.ok(ariaService.getThreads(uid)).build();
        } catch (Exception e) {
            LOG.error("Erreur interne", e);
            return Response.status(500)
                    .entity("{\"error\":\"Erreur interne du serveur\"}")
                    .build();
        }
    }

    @POST
    @Path("/feedback")
    @Authenticated
    public Response feedback(String body) {
        try {
            return Response.ok(ariaService.postFeedback(body)).build();
        } catch (Exception e) {
            LOG.error("Erreur interne", e);
            return Response.status(500)
                    .entity("{\"error\":\"Erreur interne du serveur\"}")
                    .build();
        }
    }

    @GET
    @Path("/health")
    public Response health() {
        return Response.ok("{\"status\":\"ARIA Quarkus OK\"}").build();
    }

    private List<String> mapGroupsToModules(Set<String> groups) {
        if (groups == null) return new ArrayList<>();

        if (groups.contains("SUPER_ADMIN")) {
            return List.of(
                "énergie électrique", "eau", "gaz", "carburant",
                "alertes", "équipements/capteurs", "rapports", "dashboard"
            );
        }

        List<String> modules = new ArrayList<>();
        if (groups.contains("VIEW_ENERGY_DATA")) {
            modules.add("énergie électrique");
            modules.add("carburant");
        }
        if (groups.contains("VIEW_WATER_DATA"))                                        modules.add("eau");
        if (groups.contains("VIEW_GAS_DATA"))                                          modules.add("gaz");
        if (groups.contains("VIEW_ALERTS")   || groups.contains("MANAGE_ALERTS"))     modules.add("alertes");
        if (groups.contains("VIEW_DEVICES")  || groups.contains("MANAGE_DEVICES"))    modules.add("équipements/capteurs");
        if (groups.contains("VIEW_REPORTS")  || groups.contains("GENERATE_REPORTS"))  modules.add("rapports");
        if (groups.contains("VIEW_DASHBOARD"))                                         modules.add("dashboard");
        return modules;
    }
}
