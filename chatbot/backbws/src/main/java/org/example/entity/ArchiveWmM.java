package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.time.LocalDateTime;
import java.util.List;

/**
 * Table archive_wm_m — agrégats mensuels eau
 * Clé primaire composite : (id_device, date)
 */
@Entity
@Table(name = "archive_wm_m")
public class ArchiveWmM extends PanacheEntityBase {

    @EmbeddedId
    public ArchiveWmId id;

    @Column(name = "`index`")
    public Integer wmIndex = 0;

    @Column(name = "conso")
    public Integer conso = 0;

    @Column(name = "reverse_conso")
    public Integer reverseConso = 0;

    @Column(name = "battery_level")
    public Integer batteryLevel = 0;

    // ── Queries ───────────────────────────────────────────────────────────

    public static List<ArchiveWmM> findByDeviceAndPeriod(Integer idDevice,
                                                         LocalDateTime from,
                                                         LocalDateTime to) {
        return find("id.idDevice = ?1 AND id.date BETWEEN ?2 AND ?3 ORDER BY id.date ASC",
                idDevice, from, to).list();
    }

    public static List<ArchiveWmM> findAllByPeriod(LocalDateTime from, LocalDateTime to) {
        return find("id.date BETWEEN ?1 AND ?2 ORDER BY id.date ASC", from, to).list();
    }

    public static List<ArchiveWmM> findByDevice(Integer idDevice) {
        return find("id.idDevice = ?1 ORDER BY id.date ASC", idDevice).list();
    }

    public static Long totalConsoByDeviceAndPeriod(Integer idDevice,
                                                   LocalDateTime from,
                                                   LocalDateTime to) {
        return (Long) getEntityManager()
                .createQuery(
                        "SELECT COALESCE(SUM(a.conso), 0) FROM ArchiveWmM a " +
                                "WHERE a.id.idDevice = :dev AND a.id.date BETWEEN :from AND :to")
                .setParameter("dev", idDevice)
                .setParameter("from", from)
                .setParameter("to", to)
                .getSingleResult();
    }
}
