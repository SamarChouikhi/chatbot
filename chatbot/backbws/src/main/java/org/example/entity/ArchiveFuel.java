package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.time.LocalDateTime;
import java.util.List;

/**
 * archive_fuel — données brutes IoT par trajet/événement
 * Colonnes : id, date, id_device, lat, lon, temperture (typo DB), vitesse,
 *            consommation, distance, temps_arret
 * Devices  : 6001, 6002, 6003
 */
@Entity
@Table(name = "archive_fuel")
public class ArchiveFuel extends PanacheEntityBase {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    public Long id;

    @Column(name = "date")
    public LocalDateTime date;

    @Column(name = "id_device")
    public Integer idDevice;

    @Column(name = "lat")
    public Double lat;

    @Column(name = "lon")
    public Double lon;

    /** Colonne "temperture" — typo conservé tel quel en DB */
    @Column(name = "temperture")
    public Double temperature;

    /** Vitesse instantanée (km/h) */
    @Column(name = "vitesse")
    public Double vitesse;

    /** Consommation carburant (L) */
    @Column(name = "consommation")
    public Double consommation;

    /** Distance parcourue (km) */
    @Column(name = "distance")
    public Double distance;

    /** Temps d'arrêt moteur allumé (minutes) */
    @Column(name = "temps_arret")
    public Double tempsArret;

    // ─── Queries ───────────────────────────────────────────────────────────────

    public static List<ArchiveFuel> findByDeviceAndPeriod(
            Integer idDevice, LocalDateTime from, LocalDateTime to) {
        return find("idDevice = ?1 AND date >= ?2 AND date <= ?3 ORDER BY date",
                idDevice, from, to).list();
    }

    public static List<ArchiveFuel> findAllByPeriod(
            LocalDateTime from, LocalDateTime to) {
        return find("date >= ?1 AND date <= ?2 ORDER BY idDevice, date",
                from, to).list();
    }

    public static ArchiveFuel findLatestByDevice(Integer idDevice) {
        return find("idDevice = ?1 ORDER BY date DESC", idDevice).firstResult();
    }

    public static List<Integer> findActiveDevices() {
        return getEntityManager()
                .createQuery("SELECT DISTINCT a.idDevice FROM ArchiveFuel a ORDER BY a.idDevice",
                        Integer.class)
                .getResultList();
    }
}
