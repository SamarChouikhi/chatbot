package org.example.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

/**
 * DTOs — Module Carburant (Fuel)
 *
 * Facteurs :
 *   CO₂ Diesel : 2.68 kgCO₂eq/L  (ADEME)
 *   Prix diesel : 1.89 TND/L  (Tunisie 2025, indicatif)
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public class FuelDto {

    // ── Dernière entrée par véhicule (résumé instantané) ──────────────────────
    public static class FuelLatestDto {
        public Integer deviceId;
        public String  date;
        public String  fuelType;
        public Integer mileageKm;
        public Double  consumptionLiters;
        public Double  consumptionPercentage;
        public Double  tankCapacityLiters;
        public Double  carbonKg;
        public Double  costTnd;
        /** Rendement (L/100km) calculé sur la journée */
        public Double  efficiencyL100km;
        public String  status;   // OK | HIGH_CONSO | LOW_EFFICIENCY
    }

    // ── Données brutes archive_fuel ───────────────────────────────────────────
    public static class ArchiveFuelDto {
        public Long          id;
        public LocalDateTime date;
        public Integer       idDevice;
        public Double        lat;
        public Double        lon;
        public Double        temperature;
        public Double        vitesse;
        public Double        consommation;
        public Double        distance;
        public Double        tempsArret;
    }

    // ── Données horaires archive_fuel_h ───────────────────────────────────────
    public static class ArchiveFuelHDto {
        public Long          id;
        public LocalDateTime date;
        public Integer       idDevice;
        public Double        temperature;
        public Double        vitesse;
        public Double        consommation;
        public Double        distance;
        public Double        tempsArret;
    }

    // ── Données journalières archive_fuel_j ───────────────────────────────────
    public static class ArchiveFuelJDto {
        public Long      id;
        public LocalDate date;
        public Integer   idDevice;
        public Double    temperature;
        public Double    vitesse;
        public Double    consommation;
        public Double    distance;
        public Double    tempsArret;
    }

    // ── Données mensuelles archive_fuel_m ─────────────────────────────────────
    public static class ArchiveFuelMDto {
        public Long      id;
        public LocalDate date;
        public Integer   idDevice;
        public Double    temperature;
        public Double    vitesse;
        public Double    consommation;
        public Double    distance;
        public Double    tempsArret;
    }

    // ── fuel_consumption enrichi ──────────────────────────────────────────────
    public static class FuelConsumptionDto {
        public String  date;
        public Integer deviceId;
        public String  fuelType;
        public Integer mileageKm;
        public Double  quantityAddedLiters;
        public Double  consumptionLiters;
        public Double  consumptionPercentage;
        public Double  tankCapacityLiters;
        public Double  carbonKg;
        public Double  costTnd;
    }

    // ── Résumé dashboard par véhicule ─────────────────────────────────────────
    public static class FuelSummaryDto {
        public Integer deviceId;
        public String  lastUpdate;
        /** Consommation totale (L) sur la période */
        public Double  totalConsoL;
        /** Distance totale (km) sur la période */
        public Double  totalDistanceKm;
        /** Vitesse moyenne (km/h) */
        public Double  avgSpeedKmh;
        /** Rendement moyen (L/100km) */
        public Double  avgEfficiencyL100km;
        /** CO₂ total (kgCO₂eq) */
        public Double  co2Kg;
        /** Coût total (TND) */
        public Double  costTnd;
        /** Carburant diesel ou autre */
        public String  fuelType;
        /** Variation vs période précédente ex: "+5.2%" */
        public String  trend;
        public Integer alertCount;
    }

    // ── Point de chart ────────────────────────────────────────────────────────
    public static class FuelChartPointDto {
        public String label;
        /** Consommation (L) */
        public Double conso;
        /** Distance (km) */
        public Double distance;
        /** CO₂ (kg) */
        public Double co2;
        /** Coût (TND) */
        public Double cost;
        /** Rendement (L/100km) */
        public Double efficiency;
    }

    // ── Chart complet ─────────────────────────────────────────────────────────
    public static class FuelChartDto {
        public List<FuelChartPointDto> points;
        public Double totalConsoL;
        public Double totalDistanceKm;
        public Double totalCo2;
        public Double totalCost;
        public Double avgEfficiency;
    }

    // ── Statistiques avancées ─────────────────────────────────────────────────
    public static class FuelStatsDto {
        public Integer deviceId;
        public Double  avgDailyConsoL;
        public Double  maxDailyConsoL;
        public Double  minDailyConsoL;
        public Double  avgDailyDistanceKm;
        public Double  totalDistanceKm;
        public Double  avgEfficiencyL100km;
        public Double  avgSpeedKmh;
        public Double  totalIdleMinutes;
        public Double  variationVsPrevMonth;
        public Integer totalAlerts;
    }

    // ── Alerte carburant ──────────────────────────────────────────────────────
    public static class FuelAlertDto {
        public Integer deviceId;
        public String  date;
        /** HIGH_CONSO | LOW_EFFICIENCY | EXCESSIVE_IDLE | HIGH_SPEED */
        public String  type;
        public String  message;
        /** LOW | HIGH | CRITICAL */
        public String  severity;
        public Double  value;
    }

    // ── Comparaison de périodes ───────────────────────────────────────────────
    public static class FuelComparisonDto {
        public Double currentPeriodConso;
        public Double previousPeriodConso;
        public Double variationPercent;
        /** UP | DOWN | STABLE */
        public String trend;
    }
}
