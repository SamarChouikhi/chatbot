package org.example.resource;

import jakarta.annotation.security.RolesAllowed;
import jakarta.inject.Inject;
import jakarta.transaction.Transactional;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import org.example.dto.Devicedto;
import org.example.dto.PermissionDto;
import org.example.dto.Uuserdto;
import org.example.entity.UUser;
import org.example.service.DeviceService;
import org.example.service.UuserService;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;


@Path("/api/users")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class UserResource {

    @Inject
    UuserService service;

    @Inject
    DeviceService deviceService;

    // GET /api/users?page=0&size=10&search=xxx&blocked=true&isAdvisor=1
    @GET
    @RolesAllowed({"VIEW_USERS", "MANAGE_USERS"})
    public Response list(
            @QueryParam("page")      @DefaultValue("0")    int     page,
            @QueryParam("size")      @DefaultValue("10")   int     size,
            @QueryParam("search")                          String  search,
            @QueryParam("blocked")                         Boolean blocked,
            @QueryParam("isAdvisor")                       Integer isAdvisor) {
        Map<String, Object> result = service.list(page, size, search, blocked, isAdvisor);
        return Response.ok(result).build();
    }

    // GET /api/users/{login}
    @GET
    @Path("/{login}")
    @RolesAllowed({"VIEW_USERS", "MANAGE_USERS"})
    public Response getOne(@PathParam("login") String login) {
        return Response.ok(service.getOne(login)).build();
    }

    // GET /api/users/{login}/permissions
    @GET
    @Path("/{login}/permissions")
    @RolesAllowed({"VIEW_USERS", "MANAGE_USERS"})
    public Response getPermissions(@PathParam("login") String login) {
        UUser user = UUser.findByLogin(login)
            .orElseThrow(() -> new NotFoundException("Utilisateur introuvable : " + login));
        if (user.userRole == null || user.userRole.permissions == null) {
            return Response.ok(List.of()).build();
        }
        List<PermissionDto> perms = user.userRole.permissions.stream()
            .map(PermissionDto::new)
            .sorted((a, b) -> a.permission.compareTo(b.permission))
            .collect(Collectors.toList());
        return Response.ok(perms).build();
    }

    // POST /api/users
    @POST
    @Transactional
    @RolesAllowed({"SUPER_ADMIN"})
    public Response create(Uuserdto dto) {
        Uuserdto created = service.create(dto);
        return Response.status(Response.Status.CREATED).entity(created).build();
    }

    // PUT /api/users/{login}
    @PUT
    @Path("/{login}")
    @Transactional
    @RolesAllowed({"MANAGE_USERS"})
    public Response update(@PathParam("login") String login, Uuserdto dto) {
        return Response.ok(service.update(login, dto)).build();
    }

    // DELETE /api/users/{login}
    @DELETE
    @Path("/{login}")
    @Transactional
    @RolesAllowed({"MANAGE_USERS"})
    public Response delete(@PathParam("login") String login) {
        service.delete(login);
        return Response.noContent().build();
    }

    // PUT /api/users/{login}/reset-attempts
    @PUT
    @Path("/{login}/reset-attempts")
    @Transactional
    @RolesAllowed({"MANAGE_USERS"})
    public Response resetAttempts(@PathParam("login") String login) {
        service.resetAttempts(login);
        return Response.ok(Map.of("message", "Tentatives réinitialisées")).build();
    }

    // GET /api/users/{login}/devices
    @GET
    @Path("/{login}/devices")
    @RolesAllowed({"VIEW_USERS", "MANAGE_USERS", "VIEW_DEVICES", "MANAGE_DEVICES"})
    public Response getDevices(@PathParam("login") String login) {
        List<Devicedto> devices = deviceService.listByUser(login);
        return Response.ok(devices).build();
    }

    // PUT /api/users/{login}/role
    // Body: { "roleId": 2 }
    @PUT
    @Path("/{login}/role")
    @Transactional
    @RolesAllowed({"MANAGE_USERS"})
    public Response assignRole(
            @PathParam("login") String login,
            Map<String, Integer> body) {
        Integer roleId = body.get("roleId");
        return Response.ok(service.assignRole(login, roleId)).build();
    }
}