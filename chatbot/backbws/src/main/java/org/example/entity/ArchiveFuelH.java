package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.time.LocalDateTime;
import java.util.List;

/**
 * archive_fuel_h — agrégats horaires
 * Colonnes : id, date, id_device, temperture, vitesse, consommation, distance, temps_arret
 */
@Entity
@Table(name = "archive_fuel_h")
public class ArchiveFuelH extends PanacheEntityBase {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    public Long id;

    @Column(name = "date")
    public LocalDateTime date;

    @Column(name = "id_device")
    public Integer idDevice;

    @Column(name = "temperture")
    public Double temperature;

    @Column(name = "vitesse")
    public Double vitesse;

    @Column(name = "consommation")
    public Double consommation;

    @Column(name = "distance")
    public Double distance;

    @Column(name = "temps_arret")
    public Double tempsArret;

    // ─── Queries ───────────────────────────────────────────────────────────────

    public static List<ArchiveFuelH> findByDeviceAndPeriod(
            Integer idDevice, LocalDateTime from, LocalDateTime to) {
        return find("idDevice = ?1 AND date >= ?2 AND date <= ?3 ORDER BY date",
                idDevice, from, to).list();
    }

    public static List<ArchiveFuelH> findAllByPeriod(
            LocalDateTime from, LocalDateTime to) {
        return find("date >= ?1 AND date <= ?2 ORDER BY idDevice, date",
                from, to).list();
    }

    public static Double totalConsoByDeviceAndPeriod(
            Integer idDevice, LocalDateTime from, LocalDateTime to) {
        Double result = getEntityManager()
                .createQuery(
                        "SELECT COALESCE(SUM(h.consommation), 0.0) FROM ArchiveFuelH h " +
                        "WHERE h.idDevice = :dev AND h.date >= :from AND h.date <= :to",
                        Double.class)
                .setParameter("dev",  idDevice)
                .setParameter("from", from)
                .setParameter("to",   to)
                .getSingleResult();
        return result != null ? result : 0.0;
    }
}
