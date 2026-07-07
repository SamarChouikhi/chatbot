package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.io.Serializable;
import java.time.LocalDate;
import java.util.List;
import java.util.Objects;

/**
 * Table archive_en_p_j — agrégats journaliers électricité
 * Clé primaire composite : (id_device, date) — date est de type DATE (LocalDate)
 */
@Entity
@Table(name = "archive_en_p_j")
@IdClass(ArchiveEnPJ.ArchiveEnPJId.class)
public class ArchiveEnPJ extends PanacheEntityBase {

    @Id
    @Column(name = "id_device")
    public Integer idDevice;

    @Id
    @Column(name = "date")
    public LocalDate date;

    // ── Énergie active et consommation par phase (kWh) ────────────────────────
    @Column(name = "en_L1")      public Double enL1      = 0.0;
    @Column(name = "cons_en_L1") public Double consEnL1  = 0.0;
    @Column(name = "en_L2")      public Double enL2      = 0.0;
    @Column(name = "cons_en_L2") public Double consEnL2  = 0.0;
    @Column(name = "en_L3")      public Double enL3      = 0.0;
    @Column(name = "cons_en_L3") public Double consEnL3  = 0.0;
    @Column(name = "en_L4")      public Double enL4      = 0.0;
    @Column(name = "cons_en_L4") public Double consEnL4  = 0.0;
    @Column(name = "en_L5")      public Double enL5      = 0.0;
    @Column(name = "cons_en_L5") public Double consEnL5  = 0.0;
    @Column(name = "en_L6")      public Double enL6      = 0.0;
    @Column(name = "cons_en_L6") public Double consEnL6  = 0.0;

    // ── Facteur de puissance min/max/moy ──────────────────────────────────────
    @Column(name = "min_cosfi_L1") public Double minCosfiL1 = 0.0;
    @Column(name = "max_cosfi_L1") public Double maxCosfiL1 = 0.0;
    @Column(name = "moy_cosfi_L1") public Double moyCosfiL1 = 0.0;
    @Column(name = "min_cosfi_L2") public Double minCosfiL2 = 0.0;
    @Column(name = "max_cosfi_L2") public Double maxCosfiL2 = 0.0;
    @Column(name = "moy_cosfi_L2") public Double moyCosfiL2 = 0.0;
    @Column(name = "min_cosfi_L3") public Double minCosfiL3 = 0.0;
    @Column(name = "max_cosfi_L3") public Double maxCosfiL3 = 0.0;
    @Column(name = "moy_cosfi_L3") public Double moyCosfiL3 = 0.0;

    // ── THD min/max/moy ───────────────────────────────────────────────────────
    @Column(name = "min_THD_L1") public Double minThdL1 = 0.0;
    @Column(name = "max_THD_L1") public Double maxThdL1 = 0.0;
    @Column(name = "moy_THD_L1") public Double moyThdL1 = 0.0;
    @Column(name = "min_THD_L2") public Double minThdL2 = 0.0;
    @Column(name = "max_THD_L2") public Double maxThdL2 = 0.0;
    @Column(name = "moy_THD_L2") public Double moyThdL2 = 0.0;
    @Column(name = "min_THD_L3") public Double minThdL3 = 0.0;
    @Column(name = "max_THD_L3") public Double maxThdL3 = 0.0;
    @Column(name = "moy_THD_L3") public Double moyThdL3 = 0.0;

    // ── Courant RMS min/max/moy (A) ───────────────────────────────────────────
    @Column(name = "min_rms_current_L1") public Double minRmsCurrentL1 = 0.0;
    @Column(name = "max_rms_current_L1") public Double maxRmsCurrentL1 = 0.0;
    @Column(name = "moy_rms_current_L1") public Double moyRmsCurrentL1 = 0.0;
    @Column(name = "min_rms_current_L2") public Double minRmsCurrentL2 = 0.0;
    @Column(name = "max_rms_current_L2") public Double maxRmsCurrentL2 = 0.0;
    @Column(name = "moy_rms_current_L2") public Double moyRmsCurrentL2 = 0.0;
    @Column(name = "min_rms_current_L3") public Double minRmsCurrentL3 = 0.0;
    @Column(name = "max_rms_current_L3") public Double maxRmsCurrentL3 = 0.0;
    @Column(name = "moy_rms_current_L3") public Double moyRmsCurrentL3 = 0.0;

    // ── Tension RMS min/max/moy (V) ───────────────────────────────────────────
    @Column(name = "min_rms_voltage_L1") public Double minRmsVoltageL1 = 0.0;
    @Column(name = "max_rms_voltage_L1") public Double maxRmsVoltageL1 = 0.0;
    @Column(name = "moy_rms_voltage_L1") public Double moyRmsVoltageL1 = 0.0;
    @Column(name = "min_rms_voltage_L2") public Double minRmsVoltageL2 = 0.0;
    @Column(name = "max_rms_voltage_L2") public Double maxRmsVoltageL2 = 0.0;
    @Column(name = "moy_rms_voltage_L2") public Double moyRmsVoltageL2 = 0.0;
    @Column(name = "min_rms_voltage_L3") public Double minRmsVoltageL3 = 0.0;
    @Column(name = "max_rms_voltage_L3") public Double maxRmsVoltageL3 = 0.0;
    @Column(name = "moy_rms_voltage_L3") public Double moyRmsVoltageL3 = 0.0;

    // ── Puissance active min/max/moy (W) ──────────────────────────────────────
    @Column(name = "min_active_power_L1") public Double minActivePowerL1 = 0.0;
    @Column(name = "max_active_power_L1") public Double maxActivePowerL1 = 0.0;
    @Column(name = "moy_active_power_L1") public Double moyActivePowerL1 = 0.0;
    @Column(name = "min_active_power_L2") public Double minActivePowerL2 = 0.0;
    @Column(name = "max_active_power_L2") public Double maxActivePowerL2 = 0.0;
    @Column(name = "moy_active_power_L2") public Double moyActivePowerL2 = 0.0;
    @Column(name = "min_active_power_L3") public Double minActivePowerL3 = 0.0;
    @Column(name = "max_active_power_L3") public Double maxActivePowerL3 = 0.0;
    @Column(name = "moy_active_power_L3") public Double moyActivePowerL3 = 0.0;

    // ── Énergie réactive et consommation ──────────────────────────────────────
    @Column(name = "en_reactive_L1")      public Double enReactiveL1     = 0.0;
    @Column(name = "cons_en_reactive_L1") public Double consEnReactiveL1 = 0.0;
    @Column(name = "en_reactive_L2")      public Double enReactiveL2     = 0.0;
    @Column(name = "cons_en_reactive_L2") public Double consEnReactiveL2 = 0.0;
    @Column(name = "en_reactive_L3")      public Double enReactiveL3     = 0.0;
    @Column(name = "cons_en_reactive_L3") public Double consEnReactiveL3 = 0.0;

    // ── Énergie apparente et consommation ─────────────────────────────────────
    @Column(name = "en_apparent_L1")      public Double enApparentL1     = 0.0;
    @Column(name = "en_apparent_L2")      public Double enApparentL2     = 0.0;
    @Column(name = "en_apparent_L3")      public Double enApparentL3     = 0.0;
    @Column(name = "cons_en_apparent_L1") public Double consEnApparentL1 = 0.0;
    @Column(name = "cons_en_apparent_L2") public Double consEnApparentL2 = 0.0;
    @Column(name = "cons_en_apparent_L3") public Double consEnApparentL3 = 0.0;

    // ── Facteur de puissance (fp) min/max/moy ─────────────────────────────────
    @Column(name = "min_fp_L1") public Double minFpL1 = 0.0;
    @Column(name = "max_fp_L1") public Double maxFpL1 = 0.0;
    @Column(name = "moy_fp_L1") public Double moyFpL1 = 0.0;
    @Column(name = "min_fp_L2") public Double minFpL2 = 0.0;
    @Column(name = "max_fp_L2") public Double maxFpL2 = 0.0;
    @Column(name = "moy_fp_L2") public Double moyFpL2 = 0.0;
    @Column(name = "min_fp_L3") public Double minFpL3 = 0.0;
    @Column(name = "max_fp_L3") public Double maxFpL3 = 0.0;
    @Column(name = "moy_fp_L3") public Double moyFpL3 = 0.0;

    // ── Puissance apparente min/max/moy ───────────────────────────────────────
    @Column(name = "min_apparent_power_L1") public Double minApparentPowerL1 = 0.0;
    @Column(name = "max_apparent_power_L1") public Double maxApparentPowerL1 = 0.0;
    @Column(name = "moy_apparent_power_L1") public Double moyApparentPowerL1 = 0.0;
    @Column(name = "min_apparent_power_L2") public Double minApparentPowerL2 = 0.0;
    @Column(name = "max_apparent_power_L2") public Double maxApparentPowerL2 = 0.0;
    @Column(name = "moy_apparent_power_L2") public Double moyApparentPowerL2 = 0.0;
    @Column(name = "min_apparent_power_L3") public Double minApparentPowerL3 = 0.0;
    @Column(name = "max_apparent_power_L3") public Double maxApparentPowerL3 = 0.0;
    @Column(name = "moy_apparent_power_L3") public Double moyApparentPowerL3 = 0.0;

    // ── Puissance réactive min/max/moy ────────────────────────────────────────
    @Column(name = "min_reactive_power_L1") public Double minReactivePowerL1 = 0.0;
    @Column(name = "max_reactive_power_L1") public Double maxReactivePowerL1 = 0.0;
    @Column(name = "moy_reactive_power_L1") public Double moyReactivePowerL1 = 0.0;
    @Column(name = "min_reactive_power_L2") public Double minReactivePowerL2 = 0.0;
    @Column(name = "max_reactive_power_L2") public Double maxReactivePowerL2 = 0.0;
    @Column(name = "moy_reactive_power_L2") public Double moyReactivePowerL2 = 0.0;
    @Column(name = "min_reactive_power_L3") public Double minReactivePowerL3 = 0.0;
    @Column(name = "max_reactive_power_L3") public Double maxReactivePowerL3 = 0.0;
    @Column(name = "moy_reactive_power_L3") public Double moyReactivePowerL3 = 0.0;

    // ── THDC min/max/moy ──────────────────────────────────────────────────────
    @Column(name = "max_THDC_L1") public Double maxThdcL1 = 0.0;
    @Column(name = "min_THDC_L1") public Double minThdcL1 = 0.0;
    @Column(name = "moy_THDC_L1") public Double moyThdcL1 = 0.0;
    @Column(name = "max_THDC_L2") public Double maxThdcL2 = 0.0;
    @Column(name = "min_THDC_L2") public Double minThdcL2 = 0.0;
    @Column(name = "moy_THDC_L2") public Double moyThdcL2 = 0.0;
    @Column(name = "max_THDC_L3") public Double maxThdcL3 = 0.0;
    @Column(name = "min_THDC_L3") public Double minThdcL3 = 0.0;
    @Column(name = "moy_THDC_L3") public Double moyThdcL3 = 0.0;

    // ── État device ───────────────────────────────────────────────────────────
    @Column(name = "battery_level") public Integer batteryLevel = 255;

    // ── Queries ───────────────────────────────────────────────────────────────

    public static List<ArchiveEnPJ> findByDeviceAndPeriod(Integer idDevice,
                                                           LocalDate from,
                                                           LocalDate to) {
        return find("idDevice = ?1 AND date BETWEEN ?2 AND ?3 ORDER BY date ASC",
                idDevice, from, to).list();
    }

    public static List<ArchiveEnPJ> findAllByPeriod(LocalDate from, LocalDate to) {
        return find("date BETWEEN ?1 AND ?2 ORDER BY date ASC", from, to).list();
    }

    // ── Composite Key ─────────────────────────────────────────────────────────

    public static class ArchiveEnPJId implements Serializable {
        public Integer   idDevice;
        public LocalDate date;

        public ArchiveEnPJId() {}

        @Override
        public boolean equals(Object o) {
            if (this == o) return true;
            if (!(o instanceof ArchiveEnPJId)) return false;
            ArchiveEnPJId that = (ArchiveEnPJId) o;
            return Objects.equals(idDevice, that.idDevice)
                && Objects.equals(date, that.date);
        }

        @Override
        public int hashCode() { return Objects.hash(idDevice, date); }
    }
}
