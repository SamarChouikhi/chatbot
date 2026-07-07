package org.example.service;

import org.example.dto.Devicedto;
import org.example.entity.Device;
import org.example.entity.DeviceId;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.persistence.EntityManager;
import jakarta.transaction.Transactional;
import jakarta.ws.rs.NotFoundException;
import jakarta.ws.rs.WebApplicationException;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@ApplicationScoped
public class DeviceService {

    @Inject
    EntityManager em;

    // ── LIST (paginé + filtres optionnels) ────────────────────────
    public Map<String, Object> list(int page, int size, String search, Integer type) {
        StringBuilder jpql = new StringBuilder("FROM Device d WHERE 1=1");
        if (search != null && !search.isBlank())
            jpql.append(" AND (LOWER(d.nom) LIKE :search OR LOWER(d.description) LIKE :search)");
        if (type != null)
            jpql.append(" AND d.type = :type");
        jpql.append(" ORDER BY d.id ASC");

        var query = em.createQuery(jpql.toString(), Device.class);
        if (search != null && !search.isBlank())
            query.setParameter("search", "%" + search.toLowerCase() + "%");
        if (type != null)
            query.setParameter("type", type);

        long total = countFiltered(search, type);
        List<Devicedto> data = query
                .setFirstResult(page * size)
                .setMaxResults(size)
                .getResultList()
                .stream().map(Devicedto::new)
                .collect(Collectors.toList());

        return Map.of("data", data, "total", total, "page", page, "size", size);
    }

    // ── LIST BY USER ──────────────────────────────────────────────
    public List<Devicedto> listByUser(String login) {
        return em.createQuery("FROM Device d WHERE d.login = :login ORDER BY d.type ASC, d.id ASC", Device.class)
                .setParameter("login", login)
                .getResultList()
                .stream().map(Devicedto::new)
                .collect(Collectors.toList());
    }

    private long countFiltered(String search, Integer type) {
        StringBuilder jpql = new StringBuilder("SELECT COUNT(d) FROM Device d WHERE 1=1");
        if (search != null && !search.isBlank())
            jpql.append(" AND (LOWER(d.nom) LIKE :search OR LOWER(d.description) LIKE :search)");
        if (type != null)
            jpql.append(" AND d.type = :type");
        var q = em.createQuery(jpql.toString(), Long.class);
        if (search != null && !search.isBlank())
            q.setParameter("search", "%" + search.toLowerCase() + "%");
        if (type != null)
            q.setParameter("type", type);
        return q.getSingleResult();
    }

    // ── GET ONE ───────────────────────────────────────────────────
    public Devicedto getOne(Integer id, Integer adresse) {
        Device d = em.find(Device.class, new DeviceId(id, adresse));
        if (d == null) throw new NotFoundException("Device not found: id=" + id + ", adresse=" + adresse);
        return new Devicedto(d);
    }

    // ── CREATE ────────────────────────────────────────────────────
    @Transactional
    public Devicedto create(Devicedto dto) {
        Device existing = em.find(Device.class, new DeviceId(dto.id, dto.adresse));
        if (existing != null) throw new WebApplicationException("Device already exists", 409);
        Device d = toEntity(dto);
        em.persist(d);
        return new Devicedto(d);
    }

    // ── UPDATE ────────────────────────────────────────────────────
    @Transactional
    public Devicedto update(Integer id, Integer adresse, Devicedto dto) {
        Device d = em.find(Device.class, new DeviceId(id, adresse));
        if (d == null) throw new NotFoundException("Device not found");
        d.setNom(dto.nom);
        d.setDescription(dto.description);
        d.setType(dto.type);
        d.setIdEspace(dto.id_espace);
        d.setGeometry(dto.geometry);
        d.setMaxUptime(dto.max_uptime);
        d.setIdLs(dto.id_ls);
        d.setIsGeneralMeter(dto.is_general_meter);
        d.setLastSavedIndex(dto.last_saved_index);
        d.setLogin(dto.login);
        return new Devicedto(d);
    }

    // ── DELETE ────────────────────────────────────────────────────
    @Transactional
    public void delete(Integer id, Integer adresse) {
        Device d = em.find(Device.class, new DeviceId(id, adresse));
        if (d == null) throw new NotFoundException("Device not found");
        em.remove(d);
    }

    // ── HELPER ───────────────────────────────────────────────────
    private Device toEntity(Devicedto dto) {
        Device d = new Device();
        d.setId(dto.id);
        d.setAdresse(dto.adresse);
        d.setNom(dto.nom);
        d.setDescription(dto.description);
        d.setType(dto.type);
        d.setIdEspace(dto.id_espace);
        d.setGeometry(dto.geometry);
        d.setMaxUptime(dto.max_uptime);
        d.setIdLs(dto.id_ls);
        d.setIsGeneralMeter(dto.is_general_meter);
        d.setLastSavedIndex(dto.last_saved_index);
        d.setLogin(dto.login);
        return d;
    }
}