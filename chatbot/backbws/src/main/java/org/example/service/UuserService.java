package org.example.service;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.persistence.EntityManager;
import jakarta.transaction.Transactional;
import jakarta.ws.rs.NotFoundException;
import jakarta.ws.rs.WebApplicationException;
import org.example.dto.Uuserdto;
import org.example.entity.UUser;
import org.example.entity.UserRole;
import org.mindrot.jbcrypt.BCrypt;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@ApplicationScoped
public class UuserService {

    @Inject
    EntityManager em;

    // ── LIST ──────────────────────────────────────────────────────
    public Map<String, Object> list(int page, int size, String search, Boolean blocked, Integer isAdvisor) {
        StringBuilder jpql = new StringBuilder("FROM UUser u WHERE 1=1");
        if (search != null && !search.isBlank())
            jpql.append(" AND (LOWER(u.login) LIKE :search OR LOWER(u.phone) LIKE :search OR LOWER(u.loginPere) LIKE :search)");
        if (blocked != null && blocked)
            jpql.append(" AND u.blockedUntil IS NOT NULL AND u.blockedUntil > :now");
        if (isAdvisor != null)
            jpql.append(" AND u.isAdvisor = :isAdvisor");
        jpql.append(" ORDER BY u.login ASC");

        var query = em.createQuery(jpql.toString(), UUser.class);
        if (search != null && !search.isBlank())
            query.setParameter("search", "%" + search.toLowerCase() + "%");
        if (blocked != null && blocked)
            query.setParameter("now", LocalDateTime.now());
        if (isAdvisor != null)
            query.setParameter("isAdvisor", isAdvisor);

        long total = countFiltered(search, blocked, isAdvisor);
        List<Uuserdto> data = query
                .setFirstResult(page * size)
                .setMaxResults(size)
                .getResultList()
                .stream().map(Uuserdto::new)
                .collect(Collectors.toList());

        return Map.of("data", data, "total", total, "page", page, "size", size);
    }

    private long countFiltered(String search, Boolean blocked, Integer isAdvisor) {
        StringBuilder jpql = new StringBuilder("SELECT COUNT(u) FROM UUser u WHERE 1=1");
        if (search != null && !search.isBlank())
            jpql.append(" AND (LOWER(u.login) LIKE :search OR LOWER(u.phone) LIKE :search OR LOWER(u.loginPere) LIKE :search)");
        if (blocked != null && blocked)
            jpql.append(" AND u.blockedUntil IS NOT NULL AND u.blockedUntil > :now");
        if (isAdvisor != null)
            jpql.append(" AND u.isAdvisor = :isAdvisor");
        var q = em.createQuery(jpql.toString(), Long.class);
        if (search != null && !search.isBlank())
            q.setParameter("search", "%" + search.toLowerCase() + "%");
        if (blocked != null && blocked)
            q.setParameter("now", LocalDateTime.now());
        if (isAdvisor != null)
            q.setParameter("isAdvisor", isAdvisor);
        return q.getSingleResult();
    }

    // ── GET ONE ───────────────────────────────────────────────────
    public Uuserdto getOne(String login) {
        UUser u = em.find(UUser.class, login);
        if (u == null) throw new NotFoundException("User not found: " + login);
        return new Uuserdto(u);
    }

    // ── CREATE ────────────────────────────────────────────────────
    @Transactional
    public Uuserdto create(Uuserdto dto) {
        if (em.find(UUser.class, dto.login) != null)
            throw new WebApplicationException("Login already exists", 409);
        UUser u = toEntity(dto);
        em.persist(u);
        return new Uuserdto(u);
    }

    // ── UPDATE ────────────────────────────────────────────────────
    @Transactional
    public Uuserdto update(String login, Uuserdto dto) {
        UUser u = em.find(UUser.class, login);
        if (u == null) throw new NotFoundException("User not found");
        u.loginPere        = dto.loginPere;
        u.pwdExpDate       = dto.pwdExpDate;
        u.gmtPlus          = dto.gmtPlus;
        u.isAdvisor        = dto.isAdvisor;
        u.loginFb          = dto.loginFb;
        u.idFb             = dto.idFb;
        u.idFbMsg          = dto.idFbMsg;
        u.phone            = dto.phone;
        u.failedAttempts   = dto.failedAttempts;
        u.blockedUntil     = dto.blockedUntil;
        if (dto.pwd != null && !dto.pwd.isBlank())
            u.pwd = hashPassword(dto.pwd);
        if (dto.roleId != null)
            u.userRole = dto.roleId == 0 ? null : em.find(UserRole.class, dto.roleId);
        return new Uuserdto(u);
    }

    // ── DELETE ────────────────────────────────────────────────────
    @Transactional
    public void delete(String login) {
        UUser u = em.find(UUser.class, login);
        if (u == null) throw new NotFoundException("User not found");
        em.remove(u);
    }

    // ── ASSIGN ROLE ───────────────────────────────────────────────
    @Transactional
    public Uuserdto assignRole(String login, Integer roleId) {
        UUser u = em.find(UUser.class, login);
        if (u == null) throw new NotFoundException("User not found: " + login);
        u.userRole = (roleId == null || roleId == 0) ? null : em.find(UserRole.class, roleId);
        return new Uuserdto(u);
    }

    // ── RESET ATTEMPTS ────────────────────────────────────────────
    @Transactional
    public void resetAttempts(String login) {
        UUser u = em.find(UUser.class, login);
        if (u == null) throw new NotFoundException("User not found");
        u.failedAttempts = 0;
        u.blockedUntil   = null;
    }

    private String hashPassword(String raw) {
        if (raw == null || raw.isBlank()) return null;
        if (raw.startsWith("$2a$") || raw.startsWith("$2b$")) return raw; // déjà haché
        return BCrypt.hashpw(raw, BCrypt.gensalt(12));
    }

    // ── HELPER ────────────────────────────────────────────────────
    private UUser toEntity(Uuserdto dto) {
        UUser u = new UUser();
        u.login            = dto.login;
        u.pwd              = hashPassword(dto.pwd);
        u.loginPere        = dto.loginPere;
        u.pwdExpDate       = dto.pwdExpDate;   // LocalDate ✅
        u.gmtPlus          = dto.gmtPlus;
        u.isAdvisor        = dto.isAdvisor;
        u.loginFb          = dto.loginFb;
        u.idFb             = dto.idFb;
        u.idFbMsg          = dto.idFbMsg;
        u.phone            = dto.phone;
        u.failedAttempts   = dto.failedAttempts != null ? dto.failedAttempts : 0;
        u.blockedUntil     = dto.blockedUntil;
        if (dto.roleId != null && dto.roleId > 0)
            u.userRole = em.find(UserRole.class, dto.roleId);
        return u;
    }
}