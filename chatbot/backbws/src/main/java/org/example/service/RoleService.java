package org.example.service;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.persistence.EntityManager;
import jakarta.transaction.Transactional;
import jakarta.ws.rs.BadRequestException;
import jakarta.ws.rs.NotFoundException;
import org.example.dto.PermissionDto;
import org.example.dto.RoleDto;
import org.example.entity.Permission;
import org.example.entity.UserRole;

import java.util.List;
import java.util.stream.Collectors;

@ApplicationScoped
public class RoleService {

    @Inject
    EntityManager em;

    // ── Roles ────────────────────────────────────────────────────

    public List<RoleDto> listRoles() {
        return em.createQuery("FROM UserRole r ORDER BY r.id", UserRole.class)
            .getResultList()
            .stream().map(RoleDto::new)
            .collect(Collectors.toList());
    }

    public RoleDto getRole(Integer id) {
        UserRole r = em.find(UserRole.class, id);
        if (r == null) throw new NotFoundException("Rôle introuvable : " + id);
        return new RoleDto(r);
    }

    @Transactional
    public RoleDto createRole(String name) {
        if (name == null || name.isBlank())
            throw new BadRequestException("Le nom du rôle est requis.");
        String normalized = name.trim().toUpperCase();
        if (UserRole.findByName(normalized) != null)
            throw new BadRequestException("Un rôle avec ce nom existe déjà.");
        UserRole role = new UserRole();
        role.userName = normalized;
        em.persist(role);
        return new RoleDto(role);
    }

    @Transactional
    public RoleDto updateRole(Integer id, String name) {
        UserRole role = em.find(UserRole.class, id);
        if (role == null) throw new NotFoundException("Rôle introuvable : " + id);
        if (name == null || name.isBlank())
            throw new BadRequestException("Le nom du rôle est requis.");
        String normalized = name.trim().toUpperCase();
        UserRole existing = UserRole.findByName(normalized);
        if (existing != null && !existing.id.equals(id))
            throw new BadRequestException("Un rôle avec ce nom existe déjà.");
        role.userName = normalized;
        em.merge(role);
        return new RoleDto(role);
    }

    @Transactional
    public void deleteRole(Integer id) {
        UserRole role = em.find(UserRole.class, id);
        if (role == null) throw new NotFoundException("Rôle introuvable : " + id);
        Long count = (Long) em.createQuery(
                "SELECT COUNT(u) FROM UUser u WHERE u.userRole = :role")
            .setParameter("role", role)
            .getSingleResult();
        if (count > 0)
            throw new BadRequestException(
                "Ce rôle est assigné à " + count + " utilisateur(s). Réassignez-les avant de supprimer.");
        role.permissions.clear();
        em.merge(role);
        em.flush();
        em.remove(role);
    }

    // ── Permissions ──────────────────────────────────────────────

    public List<PermissionDto> listPermissions() {
        return em.createQuery("FROM Permission p ORDER BY p.permission", Permission.class)
            .getResultList()
            .stream().map(PermissionDto::new)
            .collect(Collectors.toList());
    }

    @Transactional
    public PermissionDto createPermission(String name) {
        if (name == null || name.isBlank())
            throw new BadRequestException("Le nom de la permission est requis.");
        String normalized = name.trim().toUpperCase();
        if (Permission.findByName(normalized) != null)
            throw new BadRequestException("Une permission avec ce nom existe déjà.");
        Permission p = new Permission();
        p.permission = normalized;
        em.persist(p);
        return new PermissionDto(p);
    }

    @Transactional
    public PermissionDto updatePermission(Integer id, String name) {
        Permission p = em.find(Permission.class, id);
        if (p == null) throw new NotFoundException("Permission introuvable : " + id);
        if (name == null || name.isBlank())
            throw new BadRequestException("Le nom de la permission est requis.");
        String normalized = name.trim().toUpperCase();
        Permission existing = Permission.findByName(normalized);
        if (existing != null && !existing.id.equals(id))
            throw new BadRequestException("Une permission avec ce nom existe déjà.");
        p.permission = normalized;
        em.merge(p);
        return new PermissionDto(p);
    }

    @Transactional
    public void deletePermission(Integer id) {
        Permission p = em.find(Permission.class, id);
        if (p == null) throw new NotFoundException("Permission introuvable : " + id);
        em.createNativeQuery(
                "DELETE FROM bw_samar.userRole_permission WHERE permission_id = :pid")
            .setParameter("pid", id)
            .executeUpdate();
        em.remove(em.contains(p) ? p : em.merge(p));
    }

    @Transactional
    public RoleDto updatePermissions(Integer roleId, List<Integer> permissionIds) {
        UserRole role = em.find(UserRole.class, roleId);
        if (role == null) throw new NotFoundException("Rôle introuvable : " + roleId);
        role.permissions.clear();
        em.flush(); // force DELETEs before INSERTs to avoid join-table unique constraint violation
        if (permissionIds != null) {
            for (Integer pid : permissionIds) {
                Permission p = em.find(Permission.class, pid);
                if (p != null) role.permissions.add(p);
            }
        }
        return new RoleDto(role);
    }
}
