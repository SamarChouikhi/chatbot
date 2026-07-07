package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.time.LocalDateTime;
import java.util.List;

/**
 * Table archive_gm_h — agrégats horaires gaz
 * Clé primaire composite : (id_device, date)
 */
@Entity
@Table(name = "archive_gm_h")
public class ArchiveGmH extends PanacheEntityBase {

    @EmbeddedId
    public ArchiveGmId id;

    @Column(name = "index")
    public Integer index = 0;

    @Column(name = "conso")
    public Integer conso = 0;

    @Column(name = "reverse_conso")
    public Integer reverseConso = 0;

    @Column(name = "battery_level")
    public Integer batteryLevel = 0;

    @Column(name = "degres")
    public Integer degres = -1;

    @Column(name = "min_debit_per_min")
    public Double minDebitPerMin = 0.0;

    @Column(name = "max_debit_per_min")
    public Double maxDebitPerMin = 0.0;

    @Column(name = "avg_debit_per_min")
    public Double avgDebitPerMin = 0.0;

    @Column(name = "crc")
    public Integer crc = 0;

    // ── Queries ───────────────────────────────────────────────────────────

    public static List<ArchiveGmH> findByDeviceAndPeriod(Integer idDevice,
                                                         LocalDateTime from,
                                                         LocalDateTime to) {
        return find("id.idDevice = ?1 AND id.date BETWEEN ?2 AND ?3 ORDER BY id.date ASC",
                idDevice, from, to).list();
    }

    public static List<ArchiveGmH> findAllByPeriod(LocalDateTime from, LocalDateTime to) {
        return find("id.date BETWEEN ?1 AND ?2 ORDER BY id.date ASC", from, to).list();
    }

    public static Long totalConsoByDeviceAndPeriod(Integer idDevice,
                                                   LocalDateTime from,
                                                   LocalDateTime to) {
        return (Long) getEntityManager()
                .createQuery(
                        "SELECT COALESCE(SUM(a.conso), 0) FROM ArchiveGmH a " +
                                "WHERE a.id.idDevice = :dev AND a.id.date BETWEEN :from AND :to")
                .setParameter("dev", idDevice)
                .setParameter("from", from)
                .setParameter("to", to)
                .getSingleResult();
    }
}

