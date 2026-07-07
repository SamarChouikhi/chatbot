package org.example.dto;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

/**
 * DTOs du module Électricité
 * Facteur CO2  : 0.0571 kgCO2/kWh  (réseau tunisien, source STEG)
 * Tarif indicatif : 0.30 TND/kWh
 */
public class ElectricityDto {

    // ── Temps réel (rt_en_p) ──────────────────────────────────────────────────

    public static class RtEnPDto {
        public Integer       idDevice;
        public LocalDateTime date;

        // Énergie active cumulée (kWh)
        public Double enL1;
        public Double enL2;
        public Double enL3;

        // Facteur de puissance (cosfi)
        public Double cosfiL1;
        public Double cosfiL2;
        public Double cosfiL3;

        // THD tension (%)
        public Double thdL1;
        public Double thdL2;
        public Double thdL3;

        // THD courant (THDC)
        public Double thdcL1;
        public Double thdcL2;
        public Double thdcL3;

        // Courant RMS (A)
        public Double rmsCurrentL1;
        public Double rmsCurrentL2;
        public Double rmsCurrentL3;

        // Tension RMS (V)
        public Double rmsVoltageL1;
        public Double rmsVoltageL2;
        public Double rmsVoltageL3;

        // Puissance active (W)
        public Double activePowerL1;
        public Double activePowerL2;
        public Double activePowerL3;

        // Énergie réactive et apparente
        public Double enReactiveL1;
        public Double enReactiveL2;
        public Double enReactiveL3;
        public Double enApparentL1;
        public Double enApparentL2;
        public Double enApparentL3;

        // Énergie accumulée jour/mois (kWh)
        public Integer enAccumuleeJourL1;
        public Integer enAccumuleeJourL2;
        public Integer enAccumuleeJourL3;
        public Integer enAccumuleeMoisL1;
        public Integer enAccumuleeMoisL2;
        public Integer enAccumuleeMoisL3;

        // Signal & device
        public Integer rssi;
        public Integer snr;
        public Integer batteryLevel;

        // Statut calculé : "OK" | "LOW_BATTERY" | "HIGH_THD" | "LOW_COSFI"
        public String status;
    }

    // ── Mesure brute (archive_en_p) ───────────────────────────────────────────

    public static class ArchiveEnPDto {
        public Integer       idDevice;
        public LocalDateTime date;

        public Double enL1;
        public Double enL2;
        public Double enL3;

        public Double cosfiL1;
        public Double cosfiL2;
        public Double cosfiL3;

        public Double thdL1;
        public Double thdL2;
        public Double thdL3;

        public Double thdcL1;
        public Double thdcL2;
        public Double thdcL3;

        public Double rmsCurrentL1;
        public Double rmsCurrentL2;
        public Double rmsCurrentL3;

        public Double rmsVoltageL1;
        public Double rmsVoltageL2;
        public Double rmsVoltageL3;

        public Double activePowerL1;
        public Double activePowerL2;
        public Double activePowerL3;

        public Double enReactiveL1;
        public Double enReactiveL2;
        public Double enReactiveL3;

        public Integer batteryLevel;
        public Integer rssi;
        public Integer snr;
    }

    // ── Agrégat horaire (archive_en_p_h) ─────────────────────────────────────

    public static class ArchiveEnPHDto {
        public Integer       idDevice;
        public LocalDateTime date;

        // Consommation delta de la période (kWh)
        public Double consEnL1;
        public Double consEnL2;
        public Double consEnL3;
        public Double totalConsKwh;     // L1 + L2 + L3

        // Énergie cumulée
        public Double enL1;
        public Double enL2;
        public Double enL3;

        // Qualité réseau (moyennes)
        public Double moyCosfiL1;
        public Double moyCosfiL2;
        public Double moyCosfiL3;
        public Double moyThdL1;
        public Double moyThdL2;
        public Double moyThdL3;

        // Tension et courant moyens
        public Double moyRmsVoltageL1;
        public Double moyRmsVoltageL2;
        public Double moyRmsVoltageL3;
        public Double moyRmsCurrentL1;
        public Double moyRmsCurrentL2;
        public Double moyRmsCurrentL3;

        // Puissance active moyenne (W)
        public Double moyActivePowerL1;
        public Double moyActivePowerL2;
        public Double moyActivePowerL3;

        // Énergie réactive et apparente
        public Double consEnReactiveL1;
        public Double consEnReactiveL2;
        public Double consEnReactiveL3;
        public Double consEnApparentL1;
        public Double consEnApparentL2;
        public Double consEnApparentL3;

        public Integer batteryLevel;
    }

    // ── Agrégat journalier (archive_en_p_j) ──────────────────────────────────

    public static class ArchiveEnPJDto {
        public Integer   idDevice;
        public LocalDate date;

        public Double consEnL1;
        public Double consEnL2;
        public Double consEnL3;
        public Double totalConsKwh;

        public Double enL1;
        public Double enL2;
        public Double enL3;

        public Double moyCosfiL1;
        public Double moyCosfiL2;
        public Double moyCosfiL3;
        public Double minCosfiL1;
        public Double minCosfiL2;
        public Double minCosfiL3;

        public Double moyThdL1;
        public Double moyThdL2;
        public Double moyThdL3;
        public Double maxThdL1;
        public Double maxThdL2;
        public Double maxThdL3;

        public Double moyRmsVoltageL1;
        public Double moyRmsVoltageL2;
        public Double moyRmsVoltageL3;
        public Double minRmsVoltageL1;
        public Double maxRmsVoltageL1;

        public Double moyRmsCurrentL1;
        public Double moyRmsCurrentL2;
        public Double moyRmsCurrentL3;

        public Double moyActivePowerL1;
        public Double moyActivePowerL2;
        public Double moyActivePowerL3;

        public Double consEnReactiveL1;
        public Double consEnReactiveL2;
        public Double consEnReactiveL3;
        public Double consEnApparentL1;
        public Double consEnApparentL2;
        public Double consEnApparentL3;

        public Integer batteryLevel;
    }

    // ── Agrégat mensuel (archive_en_p_m) ─────────────────────────────────────

    public static class ArchiveEnPMDto {
        public Integer   idDevice;
        public LocalDate date;

        public Double consEnL1;
        public Double consEnL2;
        public Double consEnL3;
        public Double totalConsKwh;

        public Double enL1;
        public Double enL2;
        public Double enL3;

        public Double moyCosfiL1;
        public Double moyCosfiL2;
        public Double moyCosfiL3;

        public Double moyThdL1;
        public Double moyThdL2;
        public Double moyThdL3;

        public Double moyRmsVoltageL1;
        public Double moyRmsVoltageL2;
        public Double moyRmsVoltageL3;

        public Double moyRmsCurrentL1;
        public Double moyRmsCurrentL2;
        public Double moyRmsCurrentL3;

        public Double moyActivePowerL1;
        public Double moyActivePowerL2;
        public Double moyActivePowerL3;

        public Double consEnReactiveL1;
        public Double consEnReactiveL2;
        public Double consEnReactiveL3;

        public Integer batteryLevel;
    }

    // ── Init / config (init_energy) ───────────────────────────────────────────

    public static class InitEnergyDto {
        public Integer       idDevice;
        public LocalDateTime date;

        public Double enL1;
        public Double enL2;
        public Double enL3;

        public Double consHrEnL1;
        public Double consHrEnL2;
        public Double consHrEnL3;
        public Double consJrEnL1;
        public Double consJrEnL2;
        public Double consJrEnL3;
        public Double consMEnL1;
        public Double consMEnL2;
        public Double consMEnL3;

        public Double cosfiL1;
        public Double cosfiL2;
        public Double cosfiL3;

        public Integer alertState;
        public Integer highConsumptionCounter;
        public Integer excessiveConsumptionCounter;
        public Integer lowConsumptionCounter;

        public Integer infractionCosfiL1;
        public Integer infractionCosfiL2;
        public Integer infractionCosfiL3;
        public Integer infractionThdL1;
        public Integer infractionThdL2;
        public Integer infractionThdL3;

        public Integer batteryLevel;
        public Integer rssi;
        public Integer snr;
    }

    // ── Résumé / Dashboard ────────────────────────────────────────────────────

    public static class ElecSummaryDto {
        public Integer       idDevice;
        public LocalDateTime lastUpdate;

        // Consommation totale par période (kWh)
        public Double totalConsoHKwh;       // cette heure
        public Double totalConsoJKwh;       // ce jour
        public Double totalConsoMKwh;       // ce mois

        // Répartition par phase
        public Double consoL1Kwh;
        public Double consoL2Kwh;
        public Double consoL3Kwh;

        // Qualité réseau (temps réel)
        public Double avgCosfi;             // moyenne L1+L2+L3
        public Double avgThd;               // moyenne L1+L2+L3
        public Double avgVoltage;           // moyenne L1+L2+L3 (V)
        public Double avgCurrent;           // moyenne L1+L2+L3 (A)
        public Double totalActivePowerKw;   // L1+L2+L3 puissance active (kW)

        // Impact environnemental et coût
        public Double co2Kg;                // kg CO2 eq (0.0571 kgCO2/kWh)
        public Double costTnd;              // coût estimé TND

        // Alertes
        public Integer alertCount;

        // Tendance vs période précédente
        public String  trend;               // "+X%" ou "-X%"

        // État device
        public Integer batteryLevel;
        public String  status;              // "OK" | "LOW_BATTERY" | "HIGH_THD" | "LOW_COSFI"
    }

    // ── Données chart ─────────────────────────────────────────────────────────

    public static class ElecChartPointDto {
        public String  label;           // ex: "09/04" ou "Avr 2025"
        public Double  consKwh;         // kWh consommés
        public Double  consL1;          // kWh phase L1
        public Double  consL2;          // kWh phase L2
        public Double  consL3;          // kWh phase L3
        public Double  avgCosfi;        // facteur de puissance moyen
        public Double  avgThd;          // THD moyen
        public Double  avgVoltage;      // tension moyenne (V)
        public Double  co2Kg;           // kg CO2
    }

    public static class ElecChartDto {
        public List<ElecChartPointDto> points;
        public Double                  totalConsKwh;
        public Double                  totalCo2Kg;
        public Double                  totalCostTnd;
    }

    // ── Alertes ───────────────────────────────────────────────────────────────

    public static class ElecAlertDto {
        public Integer       idDevice;
        public LocalDateTime date;
        public String        type;      // "LOW_BATTERY" | "HIGH_THD" | "LOW_COSFI" | "HIGH_CONSO"
        public String        message;
        public String        severity;  // "LOW" | "HIGH" | "CRITICAL"
        public Double        value;     // valeur mesurée déclenchant l'alerte
    }

    // ── Comparaison périodes ──────────────────────────────────────────────────

    public static class ElecComparisonDto {
        public Double currentPeriodKwh;
        public Double previousPeriodKwh;
        public Double variationPercent;
        public String trend;            // "UP" | "DOWN" | "STABLE"

        // Détail CO2 et coût
        public Double currentCo2Kg;
        public Double previousCo2Kg;
        public Double currentCostTnd;
        public Double previousCostTnd;
    }

    // ── Qualité réseau par période ────────────────────────────────────────────

    public static class PowerQualityDto {
        public Integer   idDevice;
        public LocalDate date;

        public Double moyCosfiL1;
        public Double moyCosfiL2;
        public Double moyCosfiL3;
        public Double moyThdL1;
        public Double moyThdL2;
        public Double moyThdL3;
        public Double moyThdcL1;
        public Double moyThdcL2;
        public Double moyThdcL3;
        public Double moyVoltageL1;
        public Double moyVoltageL2;
        public Double moyVoltageL3;
        public Double moyCurrentL1;
        public Double moyCurrentL2;
        public Double moyCurrentL3;
    }
}
