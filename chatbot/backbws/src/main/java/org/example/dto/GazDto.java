package org.example.dto;
import java.time.LocalDateTime;
import java.util.List;
public class GazDto {
    // ── Temps réel ────────────────────────────────────────────────────────────

    public static class RtGmDto {
        public Integer idDevice;
        public LocalDateTime date;
        public Integer index;
        public Integer leak;
        public Integer fraud;
        public Integer batteryLevel;
        public Integer nAlert;
        public Double  minDebitPerMin;
        public Double  maxDebitPerMin;
        public Double  avgDebitPerMin;
        public Integer rssi;
        public Integer snr;
        public String  status;          // "OK" | "LEAK" | "FRAUD" | "ALERT"
    }

    // ── Mesure brute (archive_gm) ─────────────────────────────────────────────

    public static class ArchiveGmDto {
        public Integer       idDevice;
        public LocalDateTime date;
        public Integer       forwardFlow;
        public Integer       reverseFlow;
        public Integer       index;
        public Integer       leak;
        public Integer       fraud;
        public Integer       batteryLevel;
        public Double        minDebitPerMin;
        public Double        maxDebitPerMin;
        public Double        avgDebitPerMin;
    }

    // ── Agrégat horaire (archive_gm_h) ───────────────────────────────────────

    public static class ArchiveGmHDto {
        public Integer       idDevice;
        public LocalDateTime date;
        public Integer       conso;
        public Integer       reverseConso;
        public Integer       index;
        public Double        avgDebitPerMin;
        public Double        minDebitPerMin;
        public Double        maxDebitPerMin;
    }

    // ── Agrégat journalier (archive_gm_j) ────────────────────────────────────

    public static class ArchiveGmJDto {
        public Integer       idDevice;
        public LocalDateTime date;
        public Integer       conso;
        public Integer       reverseConso;
        public Integer       index;
        public Double        avgDebitPerMin;
        public Double        minDebitPerMin;
        public Double        maxDebitPerMin;
    }

    // ── Agrégat mensuel (archive_gm_m) ───────────────────────────────────────

    public static class ArchiveGmMDto {
        public Integer       idDevice;
        public LocalDateTime date;
        public Integer       conso;
        public Integer       reverseConso;
        public Integer       index;
        public Double        avgDebitPerMin;
    }

    // ── Init / config (init_gm) ───────────────────────────────────────────────

    public static class InitGmDto {
        public Integer       idDevice;
        public LocalDateTime date;
        public Integer       consoH;
        public Integer       consoJ;
        public Integer       consoM;
        public Integer       alertState;
        public Integer       highConsumptionCounter;
        public Integer       excessiveConsumptionCounter;
        public Integer       lowConsumptionCounter;
        public Double        avgDebitPerMin;
        public Double        minDebitPerMin;
        public Double        maxDebitPerMin;
    }

    // ── Résumé / Dashboard ────────────────────────────────────────────────────

    public static class GazSummaryDto {
        public Integer       idDevice;
        public LocalDateTime lastUpdate;
        public Long          totalConsoH;        // L consommés cette heure
        public Long          totalConsoJ;        // L consommés ce jour
        public Long          totalConsoM;        // L consommés ce mois
        public Double        avgDebit;
        public Integer       alertCount;
        public Integer       leakCount;
        public Double        co2Kg;              // kg CO2 eq (1 m³ gaz ≈ 2.04 kgCO2)
        public Double        costTnd;            // coût estimé TND
        public String        trend;              // "+X%" vs période préc.
    }

    // ── Données chart (par période) ───────────────────────────────────────────

    public static class GazChartPointDto {
        public String  label;          // ex: "09/04" ou "Avr"
        public Integer conso;          // L
        public Double  debit;          // L/min moyen
        public Double  co2;            // kgCO2
    }

    public static class GazChartDto {
        public List<GazChartPointDto> points;
        public Integer                totalConso;
        public Double                 totalCo2;
        public Double                 totalCost;
    }

    // ── Alertes gaz ───────────────────────────────────────────────────────────

    public static class GazAlertDto {
        public Integer       idDevice;
        public LocalDateTime date;
        public String        type;          // "LEAK" | "FRAUD" | "HIGH_CONSO" | "LOW_BATTERY"
        public String        message;
        public String        severity;      // "LOW" | "HIGH" | "CRITICAL"
    }

    // ── Comparaison périodes ──────────────────────────────────────────────────

    public static class GazComparisonDto {
        public Long   currentPeriodConso;
        public Long   previousPeriodConso;
        public Double variationPercent;
        public String trend;            // "UP" | "DOWN" | "STABLE"
    }
}
