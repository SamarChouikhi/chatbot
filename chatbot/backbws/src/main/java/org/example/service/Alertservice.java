package org.example.service;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.persistence.EntityManager;
import jakarta.transaction.Transactional;
import org.example.dto.Alertdto;
import org.example.entity.Alert;
import org.example.entity.Alertid;
import org.example.resource.AlertSseBroadcaster;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@ApplicationScoped
public class Alertservice {

    @Inject EntityManager em;
    @Inject AlertSseBroadcaster broadcaster;

    // ── LIST (paginated + optional filters) ──────────────────────
    public Map<String, Object> list(int page, int size, String type, Integer idDevice) {
        StringBuilder jpql = new StringBuilder("FROM Alert a WHERE 1=1");
        if (type != null && !type.isBlank())   jpql.append(" AND a.type = :type");
        if (idDevice != null)                  jpql.append(" AND a.idDevice = :idDevice");
        jpql.append(" ORDER BY a.date DESC");

        var query = em.createQuery(jpql.toString(), Alert.class);
        if (type != null && !type.isBlank())   query.setParameter("type", type);
        if (idDevice != null)                  query.setParameter("idDevice", idDevice);

        long total = countFiltered(type, idDevice);
        List<Alertdto> data = query
                .setFirstResult(page * size)
                .setMaxResults(size)
                .getResultList()
                .stream().map(Alertdto::new)
                .collect(Collectors.toList());

        return Map.of("data", data, "total", total, "page", page, "size", size);
    }

    private long countFiltered(String type, Integer idDevice) {
        StringBuilder jpql = new StringBuilder("SELECT COUNT(a) FROM Alert a WHERE 1=1");
        if (type != null && !type.isBlank())   jpql.append(" AND a.type = :type");
        if (idDevice != null)                  jpql.append(" AND a.idDevice = :idDevice");
        var q = em.createQuery(jpql.toString(), Long.class);
        if (type != null && !type.isBlank())   q.setParameter("type", type);
        if (idDevice != null)                  q.setParameter("idDevice", idDevice);
        return q.getSingleResult();
    }

    // ── GET ONE ───────────────────────────────────────────────────
    public Alertdto getOne(LocalDateTime date, Integer idDevice, String type) {
        Alert a = em.find(Alert.class, new Alertid(date, idDevice, type));
        if (a == null) throw new jakarta.ws.rs.NotFoundException("Alert not found");
        return new Alertdto(a);
    }

    // ── CREATE ────────────────────────────────────────────────────
    @Transactional
    public Alertdto create(Alertdto dto) {
        Alert a = toEntity(dto);
        em.persist(a);
        Alertdto created = new Alertdto(a);
        broadcaster.publish(created);
        return created;
    }

    // ── UPDATE ────────────────────────────────────────────────────
    @Transactional
    public Alertdto update(LocalDateTime date, Integer idDevice, String type, Alertdto dto) {
        Alert a = em.find(Alert.class, new Alertid(date, idDevice, type));
        if (a == null) throw new jakarta.ws.rs.NotFoundException("Alert not found");
        a.valeur          = dto.valeur;
        a.diff            = dto.diff;
        a.valMin          = dto.valMin;
        a.valMax          = dto.valMax;
        a.tempsInfraction = dto.tempsInfraction;
        a.message         = dto.message;
        a.messageEn       = dto.messageEn;
        a.recommendationEn = dto.recommendationEn;
        a.recommendationFr = dto.recommendationFr;
        a.from            = dto.from;
        return new Alertdto(a);
    }

    // ── DELETE ────────────────────────────────────────────────────
    @Transactional
    public void delete(LocalDateTime date, Integer idDevice, String type) {
        Alert a = em.find(Alert.class, new Alertid(date, idDevice, type));
        if (a == null) throw new jakarta.ws.rs.NotFoundException("Alert not found");
        em.remove(a);
    }

    // ── DISTINCT TYPES (for filter dropdown) ──────────────────────
    public List<String> distinctTypes() {
        return em.createQuery("SELECT DISTINCT a.type FROM Alert a ORDER BY a.type", String.class)
                .getResultList();
    }

    // ── HELPER ───────────────────────────────────────────────────
    private Alert toEntity(Alertdto dto) {
        Alert a = new Alert();
        a.date             = dto.date;
        a.idDevice         = dto.idDevice;
        a.type             = dto.type;
        a.valeur           = dto.valeur;
        a.diff             = dto.diff;
        a.valMin           = dto.valMin;
        a.valMax           = dto.valMax;
        a.tempsInfraction  = dto.tempsInfraction;
        a.message          = dto.message;
        a.messageEn        = dto.messageEn;
        a.recommendationEn = dto.recommendationEn;
        a.recommendationFr = dto.recommendationFr;
        a.from             = dto.from;
        return a;
    }
}