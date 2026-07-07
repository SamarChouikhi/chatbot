package org.example.resource;

import io.smallrye.mutiny.Multi;
import jakarta.inject.Inject;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.Context;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.sse.OutboundSseEvent;
import jakarta.ws.rs.sse.Sse;
import org.example.dto.Alertdto;
import org.example.service.Alertservice;

import java.time.LocalDateTime;
import java.util.Map;

@Path("/api/alerts")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class Alertressoure {

    @Inject Alertservice service;
    @Inject AlertSseBroadcaster broadcaster;

    // GET /api/alerts/stream  — SSE : alertes en temps réel
    @GET
    @Path("/stream")
    @Produces(MediaType.SERVER_SENT_EVENTS)
    public Multi<OutboundSseEvent> stream(@Context Sse sse) {
        return broadcaster.newStream()
                .map(json -> sse.newEventBuilder().name("alert").data(json).build());
    }

    // GET /api/alerts?page=0&size=10&type=XXX&idDevice=1
    @GET
    public Response list(
            @QueryParam("page")     @DefaultValue("0")  int page,
            @QueryParam("size")     @DefaultValue("10") int size,
            @QueryParam("type")                          String type,
            @QueryParam("idDevice")                      Integer idDevice) {
        Map<String, Object> result = service.list(page, size, type, idDevice);
        return Response.ok(result).build();
    }

    // GET /api/alerts/types
    @GET
    @Path("/types")
    public Response types() {
        return Response.ok(service.distinctTypes()).build();
    }

    // GET /api/alerts/{date}/{idDevice}/{type}
    @GET
    @Path("/{date}/{idDevice}/{type}")
    public Response getOne(
            @PathParam("date")     String dateStr,
            @PathParam("idDevice") Integer idDevice,
            @PathParam("type")     String type) {
        LocalDateTime date = LocalDateTime.parse(dateStr);
        return Response.ok(service.getOne(date, idDevice, type)).build();
    }

    // POST /api/alerts
    @POST
    public Response create(Alertdto dto) {
        Alertdto created = service.create(dto);
        return Response.status(Response.Status.CREATED).entity(created).build();
    }

    // PUT /api/alerts/{date}/{idDevice}/{type}
    @PUT
    @Path("/{date}/{idDevice}/{type}")
    public Response update(
            @PathParam("date")     String dateStr,
            @PathParam("idDevice") Integer idDevice,
            @PathParam("type")     String type,
            Alertdto dto) {
        LocalDateTime date = LocalDateTime.parse(dateStr);
        return Response.ok(service.update(date, idDevice, type, dto)).build();
    }

    // DELETE /api/alerts/{date}/{idDevice}/{type}
    @DELETE
    @Path("/{date}/{idDevice}/{type}")
    public Response delete(
            @PathParam("date")     String dateStr,
            @PathParam("idDevice") Integer idDevice,
            @PathParam("type")     String type) {
        LocalDateTime date = LocalDateTime.parse(dateStr);
        service.delete(date, idDevice, type);
        return Response.noContent().build();
    }
}