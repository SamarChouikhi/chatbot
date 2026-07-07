package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.time.LocalDateTime;
import java.util.List;

/**
 * Table archive_wm — données brutes eau (~10 min)
 * Clé primaire composite : (id_device, date)
 */
@Entity
@Table(name = "archive_wm")
public class ArchiveWm extends PanacheEntityBase {

    @EmbeddedId
    public ArchiveWmId id;

    @Column(name = "forward_flow")
    public Integer forwardFlow = 0;

    @Column(name = "reverse_flow")
    public Integer reverseFlow = 0;

    @Column(name = "tamp")
    public Integer tamp = 0;

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

    // ── Queries ───────────────────────────────────────────────────────────

    public static List<ArchiveWm> findByDeviceAndPeriod(Integer idDevice,
                                                        LocalDateTime from,
                                                        LocalDateTime to) {
        return find("id.idDevice = ?1 AND id.date BETWEEN ?2 AND ?3 ORDER BY id.date ASC",
                idDevice, from, to).list();
    }

    public static ArchiveWm findLatestByDevice(Integer idDevice) {
        return find("id.idDevice = ?1 ORDER BY id.date DESC", idDevice)
                .firstResult();
    }

    public static List<ArchiveWm> findAllByPeriod(LocalDateTime from, LocalDateTime to) {
        return find("id.date BETWEEN ?1 AND ?2 ORDER BY id.date ASC", from, to).list();
    }
}
