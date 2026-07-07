package org.example.entity;


import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Table rt_gm — données temps réel gaz
 * Clé primaire : id_device (une ligne par device)
 */
@Entity
@Table(name = "rt_gm")
public class RtGm extends PanacheEntityBase {

    @Id
    @Column(name = "id_device")
    public Integer idDevice;

    @Column(name = "date")
    public LocalDateTime date;

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

    @Column(name = "n_alert")
    public Integer nAlert = 0;

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

    public static RtGm findByDevice(Integer idDevice) {
        return findById(idDevice);
    }

    public static List<RtGm> findAllActive() {
        return listAll();
    }

    /** Devices en alerte (n_alert > 0) */
    public static List<RtGm> findWithAlerts() {
        return find("nAlert > 0").list();
    }

    /** Devices avec fuite détectée */
    public static List<RtGm> findWithLeak() {
        return find("leak = 1").list();
    }

    /** Devices avec batterie faible (< 50) */
    public static List<RtGm> findLowBattery() {
        return find("batteryLevel IS NOT NULL AND batteryLevel > 0 AND batteryLevel < 50").list();
    }
}

