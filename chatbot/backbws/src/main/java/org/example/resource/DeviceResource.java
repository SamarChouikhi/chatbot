package org.example.resource;

import jakarta.inject.Inject;
import jakarta.transaction.Transactional;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import org.example.dto.Devicedto;
import org.example.service.DeviceService;

import java.util.Map;

@Path("/api/devices")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class DeviceResource {

    @Inject
    DeviceService service;

    // GET /api/devices?page=0&size=20&search=xxx&type=1
    @GET
    public Response list(
            @QueryParam("page")   @DefaultValue("0")  int page,
            @QueryParam("size")   @DefaultValue("20") int size,
            @QueryParam("search")                      String search,
            @QueryParam("type")                        Integer type) {

        int cappedSize = Math.max(1, Math.min(size, 100));
        Map<String, Object> result = service.list(page, cappedSize, search, type);
        return Response.ok(result).build();
    }

    // GET /api/devices/{id}/{adresse}
    @GET
    @Path("/{id}/{adresse}")
    public Response getOne(@PathParam("id") Integer id,
                           @PathParam("adresse") Integer adresse) {
        return Response.ok(service.getOne(id, adresse)).build();
    }

    // POST /api/devices
    @POST
    @Transactional
    public Response create(Devicedto dto) {
        Devicedto created = service.create(dto);
        return Response.status(Response.Status.CREATED).entity(created).build();
    }

    // PUT /api/devices/{id}/{adresse}
    @PUT
    @Path("/{id}/{adresse}")
    @Transactional
    public Response update(@PathParam("id") Integer id,
                           @PathParam("adresse") Integer adresse,
                           Devicedto dto) {
        return Response.ok(service.update(id, adresse, dto)).build();
    }

    // DELETE /api/devices/{id}/{adresse}
    @DELETE
    @Path("/{id}/{adresse}")
    @Transactional
    public Response delete(@PathParam("id") Integer id,
                           @PathParam("adresse") Integer adresse) {
        service.delete(id, adresse);
        return Response.noContent().build();
    }
}