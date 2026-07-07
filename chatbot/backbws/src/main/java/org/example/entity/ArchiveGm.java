package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.time.LocalDateTime;
import java.util.List;

/**
 * Table archive_gm — données brutes gaz (toutes les ~10 min)
 * Clé primaire composite : (id_device, date)
 */
@Entity
@Table(name = "archive_gm")
public class ArchiveGm extends PanacheEntityBase {

    @EmbeddedId
    public ArchiveGmId id;

    @Column(name = "forward_flow")
    public Integer forwardFlow = 0;

    @Column(name = "reverse_flow")
    public Integer reverseFlow = 0;

    @Column(name = "tamp")
    public Integer tamp = 0;

    @Column(name = "index")
    public Integer index = 0;

    @Column(name = "leak")
    public Integer leak = 0;

    @Column(name = "fraud")
    public Integer fraud = 0;

    @Column(name = "sens")
    public Integer sens = 0;

    @Column(name = "battery_level")
    public Integer batteryLevel = 255;

    @Column(name = "ctr")
    public Integer ctr = 0;

    @Column(name = "snr")
    public Integer snr = 0;

    @Column(name = "rssi")
    public Integer rssi = 0;

    @Column(name = "gateway")
    public Integer gateway = 0;

    @Column(name = "min_debit_per_min")
    public Double minDebitPerMin = 0.0;

    @Column(name = "max_debit_per_min")
    public Double maxDebitPerMin = 0.0;

    @Column(name = "avg_debit_per_min")
    public Double avgDebitPerMin = 0.0;

    @Column(name = "crc")
    public Integer crc = 0;

    // ── Queries ───────────────────────────────────────────────────────────

    /** Toutes les mesures d'un device sur une période */
    public static List<ArchiveGm> findByDeviceAndPeriod(Integer idDevice,
                                                        LocalDateTime from,
                                                        LocalDateTime to) {
        return find("id.idDevice = ?1 AND id.date BETWEEN ?2 AND ?3 ORDER BY id.date ASC",
                idDevice, from, to).list();
    }

    /** Dernière mesure d'un device */
    public static ArchiveGm findLatestByDevice(Integer idDevice) {
        return find("id.idDevice = ?1 ORDER BY id.date DESC", idDevice)
                .firstResult();
    }

    /** Toutes les mesures de tous les devices sur une période */
    public static List<ArchiveGm> findAllByPeriod(LocalDateTime from, LocalDateTime to) {
        return find("id.date BETWEEN ?1 AND ?2 ORDER BY id.date ASC", from, to).list();
    }

    /** Consommation totale (sum forward_flow) d'un device sur une période */
    public static Long totalConsoByDeviceAndPeriod(Integer idDevice,
                                                   LocalDateTime from,
                                                   LocalDateTime to) {
        return (Long) getEntityManager()
                .createQuery(
                        "SELECT COALESCE(SUM(a.forwardFlow), 0) FROM ArchiveGm a " +
                                "WHERE a.id.idDevice = :dev AND a.id.date BETWEEN :from AND :to")
                .setParameter("dev", idDevice)
                .setParameter("from", from)
                .setParameter("to", to)
                .getSingleResult();
    }
}
