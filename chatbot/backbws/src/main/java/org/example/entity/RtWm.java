package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.time.LocalDateTime;
import java.util.List;

/**
 * Table rt_wm — données temps réel eau
 * Clé primaire : id_device (une ligne par device)
 */
@Entity
@Table(name = "rt_wm")
public class RtWm extends PanacheEntityBase {

    @Id
    @Column(name = "id_device")
    public Integer idDevice;

    @Column(name = "date")
    public LocalDateTime date;

    @Column(name = "`index`")
    public Integer wmIndex = 0;

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

    // ── Queries ───────────────────────────────────────────────────────────

    public static RtWm findByDevice(Integer idDevice) {
        return findById(idDevice);
    }

    public static List<RtWm> findAllActive() {
        return listAll();
    }

    /** Devices en alerte (n_alert > 0) */
    public static List<RtWm> findWithAlerts() {
        return find("nAlert > 0").list();
    }

    /** Devices avec fuite détectée */
    public static List<RtWm> findWithLeak() {
        return find("leak = 1").list();
    }

    /** Devices avec fraude détectée */
    public static List<RtWm> findWithFraud() {
        return find("fraud = 1").list();
    }

    /** Devices avec batterie faible (< 50) */
    public static List<RtWm> findLowBattery() {
        return find("batteryLevel IS NOT NULL AND batteryLevel > 0 AND batteryLevel < 50").list();
    }
}
