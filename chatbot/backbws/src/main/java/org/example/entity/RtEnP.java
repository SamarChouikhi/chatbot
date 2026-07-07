package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.time.LocalDateTime;
import java.util.List;

/**
 * Table rt_en_p — données temps réel électricité
 * Clé primaire : id_device (une ligne par device)
 */
@Entity
@Table(name = "rt_en_p")
public class RtEnP extends PanacheEntityBase {

    @Id
    @Column(name = "id_device")
    public Integer idDevice;

    @Column(name = "date")
    public LocalDateTime date;

    // ── Énergie active cumulée (kWh) ──────────────────────────────────────────
    @Column(name = "en_L1") public Double enL1 = 0.0;
    @Column(name = "en_L2") public Double enL2 = 0.0;
    @Column(name = "en_L3") public Double enL3 = 0.0;

    // ── Facteur de puissance (cosfi) ──────────────────────────────────────────
    @Column(name = "cosfi_L1") public Double cosfiL1 = 0.0;
    @Column(name = "cosfi_L2") public Double cosfiL2 = 0.0;
    @Column(name = "cosfi_L3") public Double cosfiL3 = 0.0;

    // ── Distorsion harmonique totale (THD) ────────────────────────────────────
    @Column(name = "THD_L1") public Double thdL1 = 0.0;
    @Column(name = "THD_L2") public Double thdL2 = 0.0;
    @Column(name = "THD_L3") public Double thdL3 = 0.0;

    // ── THD courant (THDC) ────────────────────────────────────────────────────
    @Column(name = "THDC_L1") public Double thdcL1 = 0.0;
    @Column(name = "THDC_L2") public Double thdcL2 = 0.0;
    @Column(name = "THDC_L3") public Double thdcL3 = 0.0;

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

    // ── Énergie apparente ─────────────────────────────────────────────────────
    @Column(name = "en_apparent_L1") public Double enApparentL1 = 0.0;
    @Column(name = "en_apparent_L2") public Double enApparentL2 = 0.0;
    @Column(name = "en_apparent_L3") public Double enApparentL3 = 0.0;

    // ── Min/Max cosfi ─────────────────────────────────────────────────────────
    @Column(name = "min_cosfi_L1") public Double minCosfiL1 = 0.0;
    @Column(name = "max_cosfi_L1") public Double maxCosfiL1 = 0.0;
    @Column(name = "min_cosfi_L2") public Double minCosfiL2 = 0.0;
    @Column(name = "max_cosfi_L2") public Double maxCosfiL2 = 0.0;
    @Column(name = "min_cosfi_L3") public Double minCosfiL3 = 0.0;
    @Column(name = "max_cosfi_L3") public Double maxCosfiL3 = 0.0;

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
    @Column(name = "moy_apparent_power_L1") public Double moyApparentPowerL1 = 0.0;
    @Column(name = "min_apparent_power_L1") public Double minApparentPowerL1 = 0.0;
    @Column(name = "max_apparent_power_L1") public Double maxApparentPowerL1 = 0.0;
    @Column(name = "moy_apparent_power_L2") public Double moyApparentPowerL2 = 0.0;
    @Column(name = "min_apparent_power_L2") public Double minApparentPowerL2 = 0.0;
    @Column(name = "max_apparent_power_L2") public Double maxApparentPowerL2 = 0.0;
    @Column(name = "moy_apparent_power_L3") public Double moyApparentPowerL3 = 0.0;
    @Column(name = "min_apparent_power_L3") public Double minApparentPowerL3 = 0.0;
    @Column(name = "max_apparent_power_L3") public Double maxApparentPowerL3 = 0.0;

    // ── Puissance réactive min/moy/max ────────────────────────────────────────
    @Column(name = "moy_reactive_power_L1") public Double moyReactivePowerL1 = 0.0;
    @Column(name = "min_reactive_power_L1") public Double minReactivePowerL1 = 0.0;
    @Column(name = "max_reactive_power_L1") public Double maxReactivePowerL1 = 0.0;
    @Column(name = "moy_reactive_power_L2") public Double moyReactivePowerL2 = 0.0;
    @Column(name = "min_reactive_power_L2") public Double minReactivePowerL2 = 0.0;
    @Column(name = "max_reactive_power_L2") public Double maxReactivePowerL2 = 0.0;
    @Column(name = "moy_reactive_power_L3") public Double moyReactivePowerL3 = 0.0;
    @Column(name = "min_reactive_power_L3") public Double minReactivePowerL3 = 0.0;
    @Column(name = "max_reactive_power_L3") public Double maxReactivePowerL3 = 0.0;

    // ── Puissance active min/max ──────────────────────────────────────────────
    @Column(name = "min_active_power_L1") public Double minActivePowerL1 = 0.0;
    @Column(name = "max_active_power_L1") public Double maxActivePowerL1 = 0.0;
    @Column(name = "min_active_power_L2") public Double minActivePowerL2 = 0.0;
    @Column(name = "max_active_power_L2") public Double maxActivePowerL2 = 0.0;
    @Column(name = "min_active_power_L3") public Double minActivePowerL3 = 0.0;
    @Column(name = "max_active_power_L3") public Double maxActivePowerL3 = 0.0;

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

    // ── THDC min/max ──────────────────────────────────────────────────────────
    @Column(name = "min_THDC_L1") public Double minThdcL1 = 0.0;
    @Column(name = "max_THDC_L1") public Double maxThdcL1 = 0.0;
    @Column(name = "min_THDC_L2") public Double minThdcL2 = 0.0;
    @Column(name = "max_THDC_L2") public Double maxThdcL2 = 0.0;
    @Column(name = "min_THDC_L3") public Double minThdcL3 = 0.0;
    @Column(name = "max_THDC_L3") public Double maxThdcL3 = 0.0;

    // ── THD min/max ───────────────────────────────────────────────────────────
    @Column(name = "min_THD_L1") public Double minThdL1 = 0.0;
    @Column(name = "max_THD_L1") public Double maxThdL1 = 0.0;
    @Column(name = "min_THD_L2") public Double minThdL2 = 0.0;
    @Column(name = "max_THD_L2") public Double maxThdL2 = 0.0;
    @Column(name = "min_THD_L3") public Double minThdL3 = 0.0;
    @Column(name = "max_THD_L3") public Double maxThdL3 = 0.0;

    // ── Signal et état device ─────────────────────────────────────────────────
    @Column(name = "rssi")          public Integer rssi         = 0;
    @Column(name = "snr")           public Integer snr          = 0;
    @Column(name = "ctr")           public Integer ctr          = 0;
    @Column(name = "battery_level") public Integer batteryLevel = 255;
    @Column(name = "gateway")       public Integer gateway      = 0;
    @Column(name = "nsh")           public Integer nsh          = 0;
    @Column(name = "tts")           public Integer tts          = 0;
    @Column(name = "di")            public Integer di           = 0;
    @Column(name = "degres")        public Integer degres       = -1;

    // ── Énergie accumulée jour/mois ───────────────────────────────────────────
    @Column(name = "en_accumulee_jour_L1") public Integer enAccumuleeJourL1;
    @Column(name = "en_accumulee_jour_L2") public Integer enAccumuleeJourL2;
    @Column(name = "en_accumulee_jour_L3") public Integer enAccumuleeJourL3;
    @Column(name = "en_accumulee_mois_L1") public Integer enAccumuleeMoisL1;
    @Column(name = "en_accumulee_mois_L2") public Integer enAccumuleeMoisL2;
    @Column(name = "en_accumulee_mois_L3") public Integer enAccumuleeMoisL3;

    // ── Énergie réactive par période ──────────────────────────────────────────
    @Column(name = "en_reactive_heure_L1") public Double enReactiveHeureL1 = 0.0;
    @Column(name = "en_reactive_heure_L2") public Double enReactiveHeureL2 = 0.0;
    @Column(name = "en_reactive_heure_L3") public Double enReactiveHeureL3 = 0.0;
    @Column(name = "en_reactive_jour_L1")  public Double enReactiveJourL1  = 0.0;
    @Column(name = "en_reactive_jour_L2")  public Double enReactiveJourL2  = 0.0;
    @Column(name = "en_reactive_jour_L3")  public Double enReactiveJourL3  = 0.0;
    @Column(name = "en_reactive_mois_L1")  public Double enReactiveMoisL1  = 0.0;
    @Column(name = "en_reactive_mois_L2")  public Double enReactiveMoisL2  = 0.0;
    @Column(name = "en_reactive_mois_L3")  public Double enReactiveMoisL3  = 0.0;

    // ── Queries ───────────────────────────────────────────────────────────────

    public static RtEnP findByDevice(Integer idDevice) {
        return findById(idDevice);
    }

    public static List<RtEnP> findAllActive() {
        return listAll();
    }

    public static List<RtEnP> findLowBattery() {
        return find("batteryLevel IS NOT NULL AND batteryLevel > 0 AND batteryLevel < 50").list();
    }

    public static List<RtEnP> findHighTHD(double threshold) {
        return find("thdL1 > ?1 OR thdL2 > ?1 OR thdL3 > ?1", threshold).list();
    }

    public static List<RtEnP> findLowCosfi(double threshold) {
        return find("(cosfiL1 > 0 AND cosfiL1 < ?1) OR (cosfiL2 > 0 AND cosfiL2 < ?1) OR (cosfiL3 > 0 AND cosfiL3 < ?1)", threshold).list();
    }
}
