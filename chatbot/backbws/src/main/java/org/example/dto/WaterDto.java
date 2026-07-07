package org.example.dto;

import java.time.LocalDateTime;
import java.util.List;

public class WaterDto {

    // ── Temps réel (rt_wm) ────────────────────────────────────────────────────

    public static class RtWmDto {
        public Integer       idDevice;
        public LocalDateTime date;
        public Integer       wmIndex;
        public Integer       leak;
        public Integer       fraud;
        public Integer       batteryLevel;
        public Integer       nAlert;
        public Integer       rssi;
        public Integer       snr;
        public String        status;      // "OK" | "LEAK" | "FRAUD" | "ALERT"
    }

    // ── Mesure brute (archive_wm) ─────────────────────────────────────────────

    public static class ArchiveWmDto {
        public Integer       idDevice;
        public LocalDateTime date;
        public Integer       forwardFlow;
        public Integer       reverseFlow;
        public Integer       wmIndex;
        public Integer       leak;
        public Integer       fraud;
        public Integer       batteryLevel;
        public Integer       rssi;
        public Integer       snr;
    }

    // ── Agrégat horaire (archive_wm_h) ───────────────────────────────────────

    public static class ArchiveWmHDto {
        public Integer       idDevice;
        public LocalDateTime date;
        public Integer       conso;           // litres consommés
        public Integer       reverseConso;
        public Integer       wmIndex;
        public Integer       batteryLevel;
    }

    // ── Agrégat journalier (archive_wm_j) ────────────────────────────────────

    public static class ArchiveWmJDto {
        public Integer       idDevice;
        public LocalDateTime date;
        public Integer       conso;
        public Integer       reverseConso;
        public Integer       wmIndex;
        public Integer       batteryLevel;
    }

    // ── Agrégat mensuel (archive_wm_m) ───────────────────────────────────────

    public static class ArchiveWmMDto {
        public Integer       idDevice;
        public LocalDateTime date;
        public Integer       conso;
        public Integer       reverseConso;
        public Integer       wmIndex;
        public Integer       batteryLevel;
    }

    // ── Init / config (init_wm) ───────────────────────────────────────────────

    public static class InitWmDto {
        public Integer       idDevice;
        public LocalDateTime date;
        public Integer       consoH;
        public Integer       consoJ;
        public Integer       consoM;
        public Integer       reverseConsoH;
        public Integer       reverseConsoJ;
        public Integer       reverseConsoM;
        public Integer       infractionConsoH;
        public Integer       infractionConsoJ;
        public Integer       infractionConsoM;
        public Integer       alertState;
        public Integer       highConsumptionCounter;
        public Integer       excessiveConsumptionCounter;
        public Integer       lowConsumptionCounter;
    }

    // ── Résumé / Dashboard ────────────────────────────────────────────────────

    public static class WaterSummaryDto {
        public Integer       idDevice;
        public LocalDateTime lastUpdate;
        public Long          totalConsoH;        // L consommés cette heure
        public Long          totalConsoJ;        // L consommés ce jour
        public Long          totalConsoM;        // L consommés ce mois
        public Double        totalConsoM3;       // m³ consommés ce mois
        public Integer       alertCount;
        public Integer       leakCount;
        public Integer       fraudCount;
        public Double        co2Kg;              // kg CO2eq (traitement eau ~0.3 kgCO2/m³)
        public Double        costTnd;            // coût estimé TND
        public String        trend;              // "+X%" vs période précédente
    }

    // ── Données chart ─────────────────────────────────────────────────────────

    public static class WaterChartPointDto {
        public String  label;          // ex: "09/04" ou "Avr"
        public Integer conso;          // litres
        public Double  consoM3;        // m³
        public Double  co2;            // kgCO2eq
        public Double  cost;           // TND
    }

    public static class WaterChartDto {
        public List<WaterChartPointDto> points;
        public Integer                  totalConsoL;
        public Double                   totalConsoM3;
        public Double                   totalCo2;
        public Double                   totalCost;
    }

    // ── Statistiques avancées ─────────────────────────────────────────────────

    public static class WaterStatsDto {
        public Integer       idDevice;
        public Long          avgDailyConsoL;     // moyenne journalière sur la période (L)
        public Long          maxDailyConsoL;     // pic journalier
        public Long          minDailyConsoL;     // journée minimale
        public Long          avgMonthlyConsoL;   // moyenne mensuelle
        public Integer       daysWithLeak;       // nombre de jours avec alerte fuite
        public Integer       totalAlerts;
        public Double        variationVsPrevMonth; // % vs mois précédent
    }

    // ── Alertes eau ───────────────────────────────────────────────────────────

    public static class WaterAlertDto {
        public Integer       idDevice;
        public LocalDateTime date;
        public String        type;       // "LEAK" | "FRAUD" | "HIGH_CONSO" | "LOW_BATTERY"
        public String        message;
        public String        severity;   // "LOW" | "HIGH" | "CRITICAL"
    }

    // ── Comparaison périodes ──────────────────────────────────────────────────

    public static class WaterComparisonDto {
        public Long   currentPeriodConso;
        public Long   previousPeriodConso;
        public Double variationPercent;
        public String trend;             // "UP" | "DOWN" | "STABLE"
    }
}
