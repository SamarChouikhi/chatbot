package org.example.resource;

import jakarta.inject.Inject;
import jakarta.transaction.Transactional;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import org.example.service.RoleService;

import java.util.List;
import java.util.Map;

record ErrorMsg(String message) {}

@Path("/api/roles")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class RoleResource {

    @Inject
    RoleService service;

    // ── Roles ────────────────────────────────────────────────────

    @GET
    public Response listRoles() {
        return Response.ok(service.listRoles()).build();
    }

    @GET
    @Path("/{id}")
    public Response getRole(@PathParam("id") Integer id) {
        return Response.ok(service.getRole(id)).build();
    }

    @POST
    @Transactional
    public Response createRole(Map<String, String> body) {
        try {
            return Response.status(201).entity(service.createRole(body.get("userName"))).build();
        } catch (BadRequestException e) {
            return Response.status(400).entity(new ErrorMsg(e.getMessage())).build();
        }
    }

    @PUT
    @Path("/{id}")
    @Transactional
    public Response updateRole(@PathParam("id") Integer id, Map<String, String> body) {
        try {
            return Response.ok(service.updateRole(id, body.get("userName"))).build();
        } catch (BadRequestException e) {
            return Response.status(400).entity(new ErrorMsg(e.getMessage())).build();
        }
    }

    @DELETE
    @Path("/{id}")
    @Transactional
    public Response deleteRole(@PathParam("id") Integer id) {
        try {
            service.deleteRole(id);
            return Response.noContent().build();
        } catch (BadRequestException e) {
            return Response.status(400).entity(new ErrorMsg(e.getMessage())).build();
        }
    }

    // ── Permissions ──────────────────────────────────────────────

    @GET
    @Path("/permissions")
    public Response listPermissions() {
        return Response.ok(service.listPermissions()).build();
    }

    @POST
    @Path("/permissions")
    @Transactional
    public Response createPermission(Map<String, String> body) {
        try {
            return Response.status(201).entity(service.createPermission(body.get("permission"))).build();
        } catch (BadRequestException e) {
            return Response.status(400).entity(new ErrorMsg(e.getMessage())).build();
        }
    }

    @PUT
    @Path("/permissions/{id}")
    @Transactional
    public Response updatePermission(@PathParam("id") Integer id, Map<String, String> body) {
        try {
            return Response.ok(service.updatePermission(id, body.get("permission"))).build();
        } catch (BadRequestException e) {
            return Response.status(400).entity(new ErrorMsg(e.getMessage())).build();
        }
    }

    @DELETE
    @Path("/permissions/{id}")
    @Transactional
    public Response deletePermission(@PathParam("id") Integer id) {
        try {
            service.deletePermission(id);
            return Response.noContent().build();
        } catch (BadRequestException e) {
            return Response.status(400).entity(new ErrorMsg(e.getMessage())).build();
        }
    }

    // ── Role-Permission assignment ────────────────────────────────

    @PUT
    @Path("/{id}/permissions")
    @Transactional
    public Response updatePermissions(
            @PathParam("id") Integer id,
            Map<String, List<Integer>> body) {
        List<Integer> permissionIds = body.get("permissionIds");
        return Response.ok(service.updatePermissions(id, permissionIds)).build();
    }
}
