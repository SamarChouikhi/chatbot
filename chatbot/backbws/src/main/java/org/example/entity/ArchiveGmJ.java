package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.time.LocalDateTime;
import java.util.List;

/**
 * Table archive_gm_j — agrégats journaliers gaz
 */
@Entity
@Table(name = "archive_gm_j")
public class ArchiveGmJ extends PanacheEntityBase {

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

    @Column(name = "min_debit_per_min")
    public Double minDebitPerMin = 0.0;

    @Column(name = "max_debit_per_min")
    public Double maxDebitPerMin = 0.0;

    @Column(name = "avg_debit_per_min")
    public Double avgDebitPerMin = 0.0;

    @Column(name = "crc")
    public Integer crc = 0;

    // ── Queries ───────────────────────────────────────────────────────────

    public static List<ArchiveGmJ> findByDeviceAndPeriod(Integer idDevice,
                                                         LocalDateTime from,
                                                         LocalDateTime to) {
        return find("id.idDevice = ?1 AND id.date BETWEEN ?2 AND ?3 ORDER BY id.date ASC",
                idDevice, from, to).list();
    }

    public static List<ArchiveGmJ> findAllByPeriod(LocalDateTime from, LocalDateTime to) {
        return find("id.date BETWEEN ?1 AND ?2 ORDER BY id.date ASC", from, to).list();
    }

    /** Consommation journalière pour un device sur N jours */
    public static List<Object[]> dailyConsoByDevice(Integer idDevice,
                                                    LocalDateTime from,
                                                    LocalDateTime to) {
        return getEntityManager()
                .createQuery(
                        "SELECT a.id.date, a.conso FROM ArchiveGmJ a " +
                                "WHERE a.id.idDevice = :dev AND a.id.date BETWEEN :from AND :to " +
                                "ORDER BY a.id.date ASC", Object[].class)
                .setParameter("dev", idDevice)
                .setParameter("from", from)
                .setParameter("to", to)
                .getResultList();
    }
}
