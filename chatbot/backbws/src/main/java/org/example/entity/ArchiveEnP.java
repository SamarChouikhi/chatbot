package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.io.Serializable;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Objects;

/**
 * Table archive_en_p — mesures brutes électricité (~10 min)
 * Clé primaire composite : (id_device, date)
 */
@Entity
@Table(name = "archive_en_p")
@IdClass(ArchiveEnP.ArchiveEnPId.class)
public class ArchiveEnP extends PanacheEntityBase {

    @Id
    @Column(name = "id_device")
    public Integer idDevice;

    @Id
    @Column(name = "date")
    public LocalDateTime date;

    // ── Énergie active (kWh) ──────────────────────────────────────────────────
    @Column(name = "en_L1") public Double enL1 = 0.0;
    @Column(name = "en_L2") public Double enL2 = 0.0;
    @Column(name = "en_L3") public Double enL3 = 0.0;
    @Column(name = "en_L4") public Double enL4 = 0.0;
    @Column(name = "en_L5") public Double enL5 = 0.0;
    @Column(name = "en_L6") public Double enL6 = 0.0;

    // ── Facteur de puissance ──────────────────────────────────────────────────
    @Column(name = "cosfi_L1") public Double cosfiL1 = 0.0;
    @Column(name = "cosfi_L2") public Double cosfiL2 = 0.0;
    @Column(name = "cosfi_L3") public Double cosfiL3 = 0.0;
    @Column(name = "cosfi_L4") public Double cosfiL4 = 0.0;
    @Column(name = "cosfi_L5") public Double cosfiL5 = 0.0;
    @Column(name = "cosfi_L6") public Double cosfiL6 = 0.0;

    // ── THD ───────────────────────────────────────────────────────────────────
    @Column(name = "THD_L1") public Double thdL1 = 0.0;
    @Column(name = "THD_L2") public Double thdL2 = 0.0;
    @Column(name = "THD_L3") public Double thdL3 = 0.0;
    @Column(name = "THD_L4") public Double thdL4 = 0.0;
    @Column(name = "THD_L5") public Double thdL5 = 0.0;
    @Column(name = "THD_L6") public Double thdL6 = 0.0;

    // ── Courant RMS (A) ───────────────────────────────────────────────────────
    @Column(name = "rms_current_L1") public Double rmsCurrentL1 = 0.0;
    @Column(name = "rms_current_L2") public Double rmsCurrentL2 = 0.0;
    @Column(name = "rms_current_L3") public Double rmsCurrentL3 = 0.0;

    // ── Tension RMS (V) ───────────────────────────────────────────────────────
    @Column(name = "rms_voltage_L1") public Double rmsVoltageL1 = 0.0;
    @Column(name = "rms_voltage_L2") public Double rmsVoltageL2 = 0.0;
    @Column(name = "rms_voltage_L3") public Double rmsVoltageL3 = 0.0;

    // ── Puissance active (W) ──────────────────────────────────────────────────
    @Column(name = "active_power_L1") public Double activePowerL1 = 0.0;
    @Column(name = "active_power_L2") public Double activePowerL2 = 0.0;
    @Column(name = "active_power_L3") public Double activePowerL3 = 0.0;

    // ── Énergie réactive ──────────────────────────────────────────────────────
    @Column(name = "en_reactive_L1") public Double enReactiveL1 = 0.0;
    @Column(name = "en_reactive_L2") public Double enReactiveL2 = 0.0;
    @Column(name = "en_reactive_L3") public Double enReactiveL3 = 0.0;

    // ── THDC ──────────────────────────────────────────────────────────────────
    @Column(name = "THDC_L1") public Double thdcL1 = 0.0;
    @Column(name = "THDC_L2") public Double thdcL2 = 0.0;
    @Column(name = "THDC_L3") public Double thdcL3 = 0.0;

    // ── Min/Max tension ───────────────────────────────────────────────────────
    @Column(name = "min_rms_voltage_L1") public Double minRmsVoltageL1 = 0.0;
    @Column(name = "max_rms_voltage_L1") public Double maxRmsVoltageL1 = 0.0;
    @Column(name = "min_rms_voltage_L2") public Double minRmsVoltageL2 = 0.0;
    @Column(name = "max_rms_voltage_L2") public Double maxRmsVoltageL2 = 0.0;
    @Column(name = "min_rms_voltage_L3") public Double minRmsVoltageL3 = 0.0;
    @Column(name = "max_rms_voltage_L3") public Double maxRmsVoltageL3 = 0.0;

    // ── Min/Max courant ───────────────────────────────────────────────────────
    @Column(name = "min_rms_current_L1") public Double minRmsCurrentL1 = 0.0;
    @Column(name = "max_rms_current_L1") public Double maxRmsCurrentL1 = 0.0;
    @Column(name = "min_rms_current_L2") public Double minRmsCurrentL2 = 0.0;
    @Column(name = "max_rms_current_L2") public Double maxRmsCurrentL2 = 0.0;
    @Column(name = "min_rms_current_L3") public Double minRmsCurrentL3 = 0.0;
    @Column(name = "max_rms_current_L3") public Double maxRmsCurrentL3 = 0.0;

    // ── Puissance apparente min/moy/max ───────────────────────────────────────
    @Column(name = "min_apparent_power_L1") public Double minApparentPowerL1 = 0.0;
    @Column(name = "max_apparent_power_L1") public Double maxApparentPowerL1 = 0.0;
    @Column(name = "moy_apparent_power_L1") public Double moyApparentPowerL1 = 0.0;
    @Column(name = "min_apparent_power_L2") public Double minApparentPowerL2 = 0.0;
    @Column(name = "max_apparent_power_L2") public Double maxApparentPowerL2 = 0.0;
    @Column(name = "moy_apparent_power_L2") public Double moyApparentPowerL2 = 0.0;
    @Column(name = "min_apparent_power_L3") public Double minApparentPowerL3 = 0.0;
    @Column(name = "max_apparent_power_L3") public Double maxApparentPowerL3 = 0.0;
    @Column(name = "moy_apparent_power_L3") public Double moyApparentPowerL3 = 0.0;

    // ── Puissance active min/max ──────────────────────────────────────────────
    @Column(name = "min_active_power_L1") public Double minActivePowerL1 = 0.0;
    @Column(name = "max_active_power_L1") public Double maxActivePowerL1 = 0.0;
    @Column(name = "min_active_power_L2") public Double minActivePowerL2 = 0.0;
    @Column(name = "max_active_power_L2") public Double maxActivePowerL2 = 0.0;
    @Column(name = "min_active_power_L3") public Double minActivePowerL3 = 0.0;
    @Column(name = "max_active_power_L3") public Double maxActivePowerL3 = 0.0;

    // ── Puissance réactive min/moy/max ────────────────────────────────────────
    @Column(name = "min_reactive_power_L1") public Double minReactivePowerL1 = 0.0;
    @Column(name = "max_reactive_power_L1") public Double maxReactivePowerL1 = 0.0;
    @Column(name = "moy_reactive_power_L1") public Double moyReactivePowerL1 = 0.0;
    @Column(name = "min_reactive_power_L2") public Double minReactivePowerL2 = 0.0;
    @Column(name = "max_reactive_power_L2") public Double maxReactivePowerL2 = 0.0;
    @Column(name = "moy_reactive_power_L2") public Double moyReactivePowerL2 = 0.0;
    @Column(name = "min_reactive_power_L3") public Double minReactivePowerL3 = 0.0;
    @Column(name = "max_reactive_power_L3") public Double maxReactivePowerL3 = 0.0;
    @Column(name = "moy_reactive_power_L3") public Double moyReactivePowerL3 = 0.0;

    // ── Facteur de puissance min/moy/max ──────────────────────────────────────
    @Column(name = "min_fp_L1") public Double minFpL1 = 0.0;
    @Column(name = "max_fp_L1") public Double maxFpL1 = 0.0;
    @Column(name = "moy_fp_L1") public Double moyFpL1 = 0.0;
    @Column(name = "min_fp_L2") public Double minFpL2 = 0.0;
    @Column(name = "max_fp_L2") public Double maxFpL2 = 0.0;
    @Column(name = "moy_fp_L2") public Double moyFpL2 = 0.0;
    @Column(name = "min_fp_L3") public Double minFpL3 = 0.0;
    @Column(name = "max_fp_L3") public Double maxFpL3 = 0.0;
    @Column(name = "moy_fp_L3") public Double moyFpL3 = 0.0;

    // ── Cosfi min/max ─────────────────────────────────────────────────────────
    @Column(name = "min_cosfi_L1") public Double minCosfiL1 = 0.0;
    @Column(name = "max_cosfi_L1") public Double maxCosfiL1 = 0.0;
    @Column(name = "min_cosfi_L2") public Double minCosfiL2 = 0.0;
    @Column(name = "max_cosfi_L2") public Double maxCosfiL2 = 0.0;
    @Column(name = "min_cosfi_L3") public Double minCosfiL3 = 0.0;
    @Column(name = "max_cosfi_L3") public Double maxCosfiL3 = 0.0;

    // ── Énergie apparente ─────────────────────────────────────────────────────
    @Column(name = "en_apparent_L1") public Double enApparentL1 = 0.0;
    @Column(name = "en_apparent_L2") public Double enApparentL2 = 0.0;
    @Column(name = "en_apparent_L3") public Double enApparentL3 = 0.0;

    // ── THDC min/max ──────────────────────────────────────────────────────────
    @Column(name = "max_THDC_L1") public Double maxThdcL1 = 0.0;
    @Column(name = "min_THDC_L1") public Double minThdcL1 = 0.0;
    @Column(name = "max_THDC_L2") public Double maxThdcL2 = 0.0;
    @Column(name = "min_THDC_L2") public Double minThdcL2 = 0.0;
    @Column(name = "max_THDC_L3") public Double maxThdcL3 = 0.0;
    @Column(name = "min_THDC_L3") public Double minThdcL3 = 0.0;

    // ── THD min/max ───────────────────────────────────────────────────────────
    @Column(name = "max_THD_L1") public Double maxThdL1 = 0.0;
    @Column(name = "min_THD_L1") public Double minThdL1 = 0.0;
    @Column(name = "max_THD_L2") public Double maxThdL2 = 0.0;
    @Column(name = "min_THD_L2") public Double minThdL2 = 0.0;
    @Column(name = "max_THD_L3") public Double maxThdL3 = 0.0;
    @Column(name = "min_THD_L3") public Double minThdL3 = 0.0;

    // ── Signal et état device ─────────────────────────────────────────────────
    @Column(name = "rssi")          public Integer rssi         = 0;
    @Column(name = "snr")           public Integer snr          = 0;
    @Column(name = "ctr")           public Integer ctr          = 0;
    @Column(name = "battery_level") public Integer batteryLevel = 255;
    @Column(name = "gateway")       public Integer gateway      = 0;
    @Column(name = "nsh")           public Integer nsh          = 0;
    @Column(name = "tts")           public Integer tts          = 0;
    @Column(name = "di")            public Integer di           = 0;

    // ── Queries ───────────────────────────────────────────────────────────────

    public static List<ArchiveEnP> findByDeviceAndPeriod(Integer idDevice,
                                                          LocalDateTime from,
                                                          LocalDateTime to) {
        return find("idDevice = ?1 AND date BETWEEN ?2 AND ?3 ORDER BY date ASC",
                idDevice, from, to).list();
    }

    public static List<ArchiveEnP> findAllByPeriod(LocalDateTime from, LocalDateTime to) {
        return find("date BETWEEN ?1 AND ?2 ORDER BY date ASC", from, to).list();
    }

    public static ArchiveEnP findLatestByDevice(Integer idDevice) {
        return find("idDevice = ?1 ORDER BY date DESC", idDevice).firstResult();
    }

    // ── Composite Key ─────────────────────────────────────────────────────────

    public static class ArchiveEnPId implements Serializable {
        public Integer       idDevice;
        public LocalDateTime date;

        public ArchiveEnPId() {}

        @Override
        public boolean equals(Object o) {
            if (this == o) return true;
            if (!(o instanceof ArchiveEnPId)) return false;
            ArchiveEnPId that = (ArchiveEnPId) o;
            return Objects.equals(idDevice, that.idDevice)
                && Objects.equals(date, that.date);
        }

        @Override
        public int hashCode() { return Objects.hash(idDevice, date); }
    }
}
