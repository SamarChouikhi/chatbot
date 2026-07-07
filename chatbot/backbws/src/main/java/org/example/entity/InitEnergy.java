package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * Table init_energy — configuration et état initial des compteurs électricité
 * Clé primaire : id_device
 * Note : seuls les champs scalaires essentiels sont mappés (les colonnes JSON sont ignorées).
 */
@Entity
@Table(name = "init_energy")
public class InitEnergy extends PanacheEntityBase {

    @Id
    @Column(name = "id_device")
    public Integer idDevice;

    @Column(name = "date")
    public LocalDateTime date;

    // ── Énergie active de référence (kWh) ─────────────────────────────────────
    @Column(name = "en_L1") public Double enL1 = 0.0;
    @Column(name = "en_L2") public Double enL2 = 0.0;
    @Column(name = "en_L3") public Double enL3 = 0.0;

    // ── Consommation horaire de référence ─────────────────────────────────────
    @Column(name = "cons_hr_en_L1") public Double consHrEnL1 = 0.0;
    @Column(name = "cons_hr_en_L2") public Double consHrEnL2 = 0.0;
    @Column(name = "cons_hr_en_L3") public Double consHrEnL3 = 0.0;

    // ── Consommation journalière de référence ─────────────────────────────────
    @Column(name = "cons_jr_en_L1") public Double consJrEnL1 = 0.0;
    @Column(name = "cons_jr_en_L2") public Double consJrEnL2 = 0.0;
    @Column(name = "cons_jr_en_L3") public Double consJrEnL3 = 0.0;

    // ── Consommation mensuelle de référence ───────────────────────────────────
    @Column(name = "cons_m_en_L1") public Double consMEnL1 = 0.0;
    @Column(name = "cons_m_en_L2") public Double consMEnL2 = 0.0;
    @Column(name = "cons_m_en_L3") public Double consMEnL3 = 0.0;

    // ── Facteur de puissance de référence ─────────────────────────────────────
    @Column(name = "cosfi_L1") public Double cosfiL1 = 0.0;
    @Column(name = "cosfi_L2") public Double cosfiL2 = 0.0;
    @Column(name = "cosfi_L3") public Double cosfiL3 = 0.0;

    // ── THD de référence ──────────────────────────────────────────────────────
    @Column(name = "THD_L1") public Double thdL1 = 0.0;
    @Column(name = "THD_L2") public Double thdL2 = 0.0;
    @Column(name = "THD_L3") public Double thdL3 = 0.0;

    // ── THDC de référence ─────────────────────────────────────────────────────
    @Column(name = "THDC_L1") public Double thdcL1 = 0.0;
    @Column(name = "THDC_L2") public Double thdcL2 = 0.0;
    @Column(name = "THDC_L3") public Double thdcL3 = 0.0;

    // ── Signal et état device ─────────────────────────────────────────────────
    @Column(name = "rssi")          public Integer rssi         = 0;
    @Column(name = "snr")           public Integer snr          = 0;
    @Column(name = "ctr")           public Integer ctr          = 0;
    @Column(name = "battery_level") public Integer batteryLevel = 255;
    @Column(name = "gateway")       public Integer gateway      = 0;

    // ── État des alertes ──────────────────────────────────────────────────────
    @Column(name = "alert_state")                  public Integer alertState                 = 0;
    @Column(name = "high_consumption_counter")     public Integer highConsumptionCounter     = 0;
    @Column(name = "excessive_consumption_counter") public Integer excessiveConsumptionCounter = 0;
    @Column(name = "low_consumption_counter")      public Integer lowConsumptionCounter      = 0;
    @Column(name = "low_cons_alert_state")         public Integer lowConsAlertState          = 0;
    @Column(name = "high_cons_alert_state")        public Integer highConsAlertState         = 0;

    // ── Infractions cosfi ─────────────────────────────────────────────────────
    @Column(name = "infraction_cosfi_L1") public Integer infractionCosfiL1 = 0;
    @Column(name = "infraction_cosfi_L2") public Integer infractionCosfiL2 = 0;
    @Column(name = "infraction_cosfi_L3") public Integer infractionCosfiL3 = 0;

    // ── Infractions THD ───────────────────────────────────────────────────────
    @Column(name = "infraction_thd_L1") public Integer infractionThdL1 = 0;
    @Column(name = "infraction_thd_L2") public Integer infractionThdL2 = 0;
    @Column(name = "infraction_thd_L3") public Integer infractionThdL3 = 0;

    // ── Infractions consommation horaire ──────────────────────────────────────
    @Column(name = "infraction_conso_h_L1") public Integer infractionConsoHL1 = 0;
    @Column(name = "infraction_conso_h_L2") public Integer infractionConsoHL2 = 0;
    @Column(name = "infraction_conso_h_L3") public Integer infractionConsoHL3 = 0;

    // ── Infractions consommation journalière ──────────────────────────────────
    @Column(name = "infraction_conso_j_L1") public Integer infractionConsoJL1 = 0;
    @Column(name = "infraction_conso_j_L2") public Integer infractionConsoJL2 = 0;
    @Column(name = "infraction_conso_j_L3") public Integer infractionConsoJL3 = 0;

    // ── Infractions consommation mensuelle ────────────────────────────────────
    @Column(name = "infraction_conso_m_L1") public Integer infractionConsoML1 = 0;
    @Column(name = "infraction_conso_m_L2") public Integer infractionConsoML2 = 0;
    @Column(name = "infraction_conso_m_L3") public Integer infractionConsoML3 = 0;

    // ── Puissance apparente et réactive de référence ──────────────────────────
    @Column(name = "moy_apparent_power_L1")  public Double moyApparentPowerL1  = 0.0;
    @Column(name = "min_apparent_power_L1")  public Double minApparentPowerL1  = 0.0;
    @Column(name = "max_apparent_power_L1")  public Double maxApparentPowerL1  = 0.0;
    @Column(name = "moy_reactive_power_L1")  public Double moyReactivePowerL1  = 0.0;
    @Column(name = "min_reactive_power_L1")  public Double minReactivePowerL1  = 0.0;
    @Column(name = "max_reactive_power_L1")  public Double maxReactivePowerL1  = 0.0;
    @Column(name = "moy_apparent_power_L2")  public Double moyApparentPowerL2  = 0.0;
    @Column(name = "min_apparent_power_L2")  public Double minApparentPowerL2  = 0.0;
    @Column(name = "max_apparent_power_L2")  public Double maxApparentPowerL2  = 0.0;
    @Column(name = "moy_reactive_power_L2")  public Double moyReactivePowerL2  = 0.0;
    @Column(name = "min_reactive_power_L2")  public Double minReactivePowerL2  = 0.0;
    @Column(name = "max_reactive_power_L2")  public Double maxReactivePowerL2  = 0.0;
    @Column(name = "moy_apparent_power_L3")  public Double moyApparentPowerL3  = 0.0;
    @Column(name = "min_apparent_power_L3")  public Double minApparentPowerL3  = 0.0;
    @Column(name = "max_apparent_power_L3")  public Double maxApparentPowerL3  = 0.0;
    @Column(name = "moy_reactive_power_L3")  public Double moyReactivePowerL3  = 0.0;
    @Column(name = "min_reactive_power_L3")  public Double minReactivePowerL3  = 0.0;
    @Column(name = "max_reactive_power_L3")  public Double maxReactivePowerL3  = 0.0;

    // ── Énergie réactive ──────────────────────────────────────────────────────
    @Column(name = "en_reactive_L1") public Double enReactiveL1 = 0.0;
    @Column(name = "en_reactive_L2") public Double enReactiveL2 = 0.0;
    @Column(name = "en_reactive_L3") public Double enReactiveL3 = 0.0;

    // ── Énergie apparente ─────────────────────────────────────────────────────
    @Column(name = "en_apparent_L1") public Double enApparentL1 = 0.0;
    @Column(name = "en_apparent_L2") public Double enApparentL2 = 0.0;
    @Column(name = "en_apparent_L3") public Double enApparentL3 = 0.0;

    // ── Date de début de vérification des alertes ─────────────────────────────
    @Column(name = "start_check_alert_date")
    public LocalDateTime startCheckAlertDate;

    // ── Queries ───────────────────────────────────────────────────────────────

    public static InitEnergy findByDevice(Integer idDevice) {
        return findById(idDevice);
    }
}
