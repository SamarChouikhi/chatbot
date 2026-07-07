package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

/**
 * archive_fuel_m — agrégats mensuels
 * Colonnes : id, date (DATE), id_device, temperture, vitesse, consommation, distance, temps_arret
 */
@Entity
@Table(name = "archive_fuel_m")
public class ArchiveFuelM extends PanacheEntityBase {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    public Long id;

    @Column(name = "date")
    public LocalDate date;

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

    public static List<ArchiveFuelM> findByDeviceAndPeriod(
            Integer idDevice, LocalDateTime from, LocalDateTime to) {
        return find("idDevice = ?1 AND date >= ?2 AND date <= ?3 ORDER BY date",
                idDevice, from.toLocalDate(), to.toLocalDate()).list();
    }

    public static List<ArchiveFuelM> findAllByPeriod(
            LocalDateTime from, LocalDateTime to) {
        return find("date >= ?1 AND date <= ?2 ORDER BY idDevice, date",
                from.toLocalDate(), to.toLocalDate()).list();
    }

    public static List<ArchiveFuelM> findByDevice(Integer idDevice) {
        return find("idDevice = ?1 ORDER BY date", idDevice).list();
    }

    public static Double totalConsoByDeviceAndPeriod(
            Integer idDevice, LocalDateTime from, LocalDateTime to) {
        Double result = getEntityManager()
                .createQuery(
                        "SELECT COALESCE(SUM(m.consommation), 0.0) FROM ArchiveFuelM m " +
                        "WHERE m.idDevice = :dev AND m.date >= :from AND m.date <= :to",
                        Double.class)
                .setParameter("dev",  idDevice)
                .setParameter("from", from.toLocalDate())
                .setParameter("to",   to.toLocalDate())
                .getSingleResult();
        return result != null ? result : 0.0;
    }
}
