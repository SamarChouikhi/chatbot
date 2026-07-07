package org.example.service;


import jakarta.enterprise.context.ApplicationScoped;
import jakarta.transaction.Transactional;
import org.example.dto.GazDto;
import org.example.dto.GazDto.*;
import org.example.entity.*;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Service métier — Module Gaz
 * Facteur CO2 gaz naturel : 2.04 kgCO2/m³  (source ADEME)
 * Facteur coût indicatif  : 0.85 TND/m³
 * 1 unité index ≈ 1 litre (L) — à adapter selon ton calibrage
 */
@ApplicationScoped
public class GazService {

    // ── Constantes ────────────────────────────────────────────────────────────
    private static final double CO2_FACTOR_PER_M3  = 2.04;   // kgCO2 / m³
    private static final double COST_PER_M3_TND    = 0.85;   // TND / m³
    private static final int    LITERS_PER_M3      = 1000;

    // ═══════════════════════════════════════════════════════════════════════════
    // TEMPS RÉEL
    // ═══════════════════════════════════════════════════════════════════════════

    /** Retourne les données RT de tous les compteurs gaz */
    public List<RtGmDto> getAllRealTime() {
        return RtGm.findAllActive()
                .stream()
                .map(this::toRtDto)
                .collect(Collectors.toList());
    }

    /** Données RT d'un compteur spécifique */
    public RtGmDto getRealTime(Integer idDevice) {
        RtGm rt = RtGm.findByDevice(idDevice);
        if (rt == null) return null;
        return toRtDto(rt);
    }

    /** Devices gaz actuellement en alerte */
    public List<RtGmDto> getDevicesWithAlerts() {
        return RtGm.findWithAlerts()
                .stream()
                .map(this::toRtDto)
                .collect(Collectors.toList());
    }

    /** Devices avec fuite détectée */
    public List<RtGmDto> getDevicesWithLeak() {
        return RtGm.findWithLeak()
                .stream()
                .map(this::toRtDto)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // BRUT (archive_gm — ~10 min)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ArchiveGmDto> getRawByDeviceAndPeriod(Integer idDevice,
                                                      LocalDateTime from,
                                                      LocalDateTime to) {
        return ArchiveGm.findByDeviceAndPeriod(idDevice, from, to)
                .stream()
                .map(this::toArchiveGmDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveGmDto> getAllRawByPeriod(LocalDateTime from, LocalDateTime to) {
        return ArchiveGm.findAllByPeriod(from, to)
                .stream()
                .map(this::toArchiveGmDto)
                .collect(Collectors.toList());
    }

    public ArchiveGmDto getLatestRaw(Integer idDevice) {
        ArchiveGm raw = ArchiveGm.findLatestByDevice(idDevice);
        if (raw == null) return null;
        return toArchiveGmDto(raw);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // HORAIRE (archive_gm_h)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ArchiveGmHDto> getHourlyByDeviceAndPeriod(Integer idDevice,
                                                          LocalDateTime from,
                                                          LocalDateTime to) {
        return ArchiveGmH.findByDeviceAndPeriod(idDevice, from, to)
                .stream()
                .map(this::toArchiveGmHDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveGmHDto> getAllHourlyByPeriod(LocalDateTime from, LocalDateTime to) {
        return ArchiveGmH.findAllByPeriod(from, to)
                .stream()
                .map(this::toArchiveGmHDto)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // JOURNALIER (archive_gm_j)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ArchiveGmJDto> getDailyByDeviceAndPeriod(Integer idDevice,
                                                         LocalDateTime from,
                                                         LocalDateTime to) {
        return ArchiveGmJ.findByDeviceAndPeriod(idDevice, from, to)
                .stream()
                .map(this::toArchiveGmJDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveGmJDto> getAllDailyByPeriod(LocalDateTime from, LocalDateTime to) {
        return ArchiveGmJ.findAllByPeriod(from, to)
                .stream()
                .map(this::toArchiveGmJDto)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // MENSUEL (archive_gm_m)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ArchiveGmMDto> getMonthlyByDevice(Integer idDevice) {
        return ArchiveGmM.findByDevice(idDevice)
                .stream()
                .map(this::toArchiveGmMDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveGmMDto> getMonthlyByDeviceAndPeriod(Integer idDevice,
                                                           LocalDateTime from,
                                                           LocalDateTime to) {
        return ArchiveGmM.findByDeviceAndPeriod(idDevice, from, to)
                .stream()
                .map(this::toArchiveGmMDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveGmMDto> getAllMonthlyByPeriod(LocalDateTime from, LocalDateTime to) {
        return ArchiveGmM.findAllByPeriod(from, to)
                .stream()
                .map(this::toArchiveGmMDto)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // INIT / CONFIG
    // ═══════════════════════════════════════════════════════════════════════════

    public InitGmDto getConfig(Integer idDevice) {
        InitGm init = InitGm.findByDevice(idDevice);
        if (init == null) return null;
        return toInitGmDto(init);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // RÉSUMÉ / DASHBOARD
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Résumé complet d'un device sur une période donnée.
     * Utile pour le widget dashboard.
     */
    public GazSummaryDto getSummary(Integer idDevice, LocalDateTime from, LocalDateTime to) {

        InitGm  init = InitGm.findByDevice(idDevice);
        RtGm    rt   = RtGm.findByDevice(idDevice);

        // Conso totale sur la période (en L)
        Long consoH = ArchiveGmH.totalConsoByDeviceAndPeriod(idDevice, from, to);
        Long consoJ = ArchiveGmJ.findByDeviceAndPeriod(idDevice, from, to)
                .stream()
                .mapToLong(r -> r.conso == null ? 0 : r.conso)
                .sum();
        // Tronquer au 1er du mois pour ne pas rater les records mensuels en début de mois
        LocalDateTime fromMonth = from.withDayOfMonth(1).withHour(0).withMinute(0).withSecond(0);
        Long consoM = ArchiveGmM.findByDeviceAndPeriod(idDevice, fromMonth, to)
                .stream()
                .mapToLong(r -> r.conso == null ? 0 : r.conso)
                .sum();

        // Fallback : si les agrégats sont vides, calculer le delta d'index depuis les données brutes
        if (consoM == 0 && consoJ == 0) {
            List<ArchiveGm> raws = ArchiveGm.findByDeviceAndPeriod(idDevice, from, to);
            if (!raws.isEmpty()) {
                long maxIdx = raws.stream().mapToLong(r -> r.index == null ? 0L : r.index.longValue()).max().orElse(0L);
                long minIdx = raws.stream().mapToLong(r -> r.index == null ? 0L : r.index.longValue()).min().orElse(0L);
                consoJ = maxIdx - minIdx;
                consoM = consoJ;
            }
        }

        // CO2 et coût (basé sur conso mensuelle totale)
        double co2  = litersToM3(consoM) * CO2_FACTOR_PER_M3;
        double cost = litersToM3(consoM) * COST_PER_M3_TND;

        // Alertes
        int alertCount = (rt != null && rt.nAlert != null) ? rt.nAlert : 0;
        int leakCount  = (rt != null && rt.leak   != null && rt.leak == 1) ? 1 : 0;

        // Calcul trend vs période précédente
        long duration = java.time.Duration.between(from, to).toDays();
        LocalDateTime prevFrom = from.minusDays(duration);
        Long prevConsoM = ArchiveGmM.findByDeviceAndPeriod(idDevice, prevFrom, from)
                .stream()
                .mapToLong(r -> r.conso == null ? 0 : r.conso)
                .sum();
        String trend = computeTrend(consoM, prevConsoM);

        GazSummaryDto dto = new GazSummaryDto();
        dto.idDevice    = idDevice;
        dto.lastUpdate  = rt != null ? rt.date : null;
        dto.totalConsoH = consoH;
        dto.totalConsoJ = consoJ;
        // Préférer la somme journalière (plus précise pour les plages qui coupent les mois)
        dto.totalConsoM = consoJ > 0 ? consoJ : consoM;
        dto.avgDebit    = rt != null ? rt.avgDebitPerMin : 0.0;
        dto.alertCount  = alertCount;
        dto.leakCount   = leakCount;
        dto.co2Kg       = Math.round(co2 * 100.0) / 100.0;
        dto.costTnd     = Math.round(cost * 100.0) / 100.0;
        dto.trend       = trend;
        return dto;
    }

    /** Résumé de tous les devices sur une période */
    public List<GazSummaryDto> getAllSummaries(LocalDateTime from, LocalDateTime to) {
        return RtGm.findAllActive()
                .stream()
                .map(rt -> getSummary(rt.idDevice, from, to))
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // CHART DATA
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Données chart journalier pour un device sur N jours.
     * Chaque point = 1 jour avec conso, débit, CO2.
     */
    public GazChartDto getDailyChart(Integer idDevice, LocalDateTime from, LocalDateTime to) {
        List<ArchiveGmJ> records = ArchiveGmJ.findByDeviceAndPeriod(idDevice, from, to);

        List<GazChartPointDto> points = records.stream().map(r -> {
            GazChartPointDto p = new GazChartPointDto();
            p.label = r.id.date.format(DateTimeFormatter.ofPattern("dd/MM"));
            p.conso = r.conso != null ? r.conso : 0;
            p.debit = r.avgDebitPerMin != null ? r.avgDebitPerMin : 0.0;
            p.co2   = Math.round(litersToM3(p.conso.longValue()) * CO2_FACTOR_PER_M3 * 100.0) / 100.0;
            return p;
        }).collect(Collectors.toList());

        long   totalConso = points.stream().mapToLong(p -> p.conso).sum();
        double totalCo2   = Math.round(litersToM3(totalConso) * CO2_FACTOR_PER_M3 * 100.0) / 100.0;
        double totalCost  = Math.round(litersToM3(totalConso) * COST_PER_M3_TND * 100.0) / 100.0;

        GazChartDto chart = new GazChartDto();
        chart.points    = points;
        chart.totalConso = (int) totalConso;
        chart.totalCo2   = totalCo2;
        chart.totalCost  = totalCost;
        return chart;
    }

    /**
     * Données chart mensuel pour un device.
     */
    public GazChartDto getMonthlyChart(Integer idDevice, LocalDateTime from, LocalDateTime to) {
        List<ArchiveGmM> records = ArchiveGmM.findByDeviceAndPeriod(idDevice, from, to);

        List<GazChartPointDto> points = records.stream().map(r -> {
            GazChartPointDto p = new GazChartPointDto();
            p.label = r.id.date.format(DateTimeFormatter.ofPattern("MM/yyyy"));
            p.conso = r.conso != null ? r.conso : 0;
            p.debit = r.avgDebitPerMin != null ? r.avgDebitPerMin : 0.0;
            p.co2   = Math.round(litersToM3(p.conso.longValue()) * CO2_FACTOR_PER_M3 * 100.0) / 100.0;
            return p;
        }).collect(Collectors.toList());

        long   totalConso = points.stream().mapToLong(p -> p.conso).sum();
        double totalCo2   = Math.round(litersToM3(totalConso) * CO2_FACTOR_PER_M3 * 100.0) / 100.0;
        double totalCost  = Math.round(litersToM3(totalConso) * COST_PER_M3_TND * 100.0) / 100.0;

        GazChartDto chart = new GazChartDto();
        chart.points     = points;
        chart.totalConso = (int) totalConso;
        chart.totalCo2   = totalCo2;
        chart.totalCost  = totalCost;
        return chart;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // ALERTES
    // ═══════════════════════════════════════════════════════════════════════════

    public List<GazAlertDto> getActiveAlerts() {
        List<GazAlertDto> alerts = new ArrayList<>();

        // Fuites
        RtGm.findWithLeak().forEach(rt -> {
            GazAlertDto a = new GazAlertDto();
            a.idDevice = rt.idDevice;
            a.date     = rt.date;
            a.type     = "LEAK";
            a.message  = "Fuite détectée sur le compteur " + rt.idDevice;
            a.severity = "CRITICAL";
            alerts.add(a);
        });

        // Fraudes
        RtGm.find("fraud = 1").stream().forEach(obj -> {
            RtGm rt = (RtGm) obj;
            GazAlertDto a = new GazAlertDto();
            a.idDevice = rt.idDevice;
            a.date     = rt.date;
            a.type     = "FRAUD";
            a.message  = "Tentative de fraude détectée sur le compteur " + rt.idDevice;
            a.severity = "CRITICAL";
            alerts.add(a);
        });

        // Batterie faible
        RtGm.findLowBattery().forEach(rt -> {
            GazAlertDto a = new GazAlertDto();
            a.idDevice = rt.idDevice;
            a.date     = rt.date;
            a.type     = "LOW_BATTERY";
            a.message  = "Batterie faible (" + rt.batteryLevel + "%) sur compteur " + rt.idDevice;
            a.severity = "HIGH";
            alerts.add(a);
        });

        return alerts;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // COMPARAISON PÉRIODES
    // ═══════════════════════════════════════════════════════════════════════════

    public GazComparisonDto compareWithPreviousPeriod(Integer idDevice,
                                                      LocalDateTime from,
                                                      LocalDateTime to) {
        long duration = java.time.Duration.between(from, to).toDays();
        LocalDateTime prevFrom = from.minusDays(duration);

        Long current = ArchiveGmJ.findByDeviceAndPeriod(idDevice, from, to)
                .stream().mapToLong(r -> r.conso == null ? 0 : r.conso).sum();
        Long previous = ArchiveGmJ.findByDeviceAndPeriod(idDevice, prevFrom, from)
                .stream().mapToLong(r -> r.conso == null ? 0 : r.conso).sum();

        GazComparisonDto dto = new GazComparisonDto();
        dto.currentPeriodConso  = current;
        dto.previousPeriodConso = previous;
        dto.variationPercent    = computeVariationPercent(current, previous);
        dto.trend = dto.variationPercent > 2 ? "UP"
                : dto.variationPercent < -2 ? "DOWN"
                : "STABLE";
        return dto;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // MAPPERS PRIVÉS
    // ═══════════════════════════════════════════════════════════════════════════

    private RtGmDto toRtDto(RtGm rt) {
        RtGmDto dto = new RtGmDto();
        dto.idDevice       = rt.idDevice;
        dto.date           = rt.date;
        dto.index          = rt.index;
        dto.leak           = rt.leak;
        dto.fraud          = rt.fraud;
        dto.batteryLevel   = rt.batteryLevel;
        dto.nAlert         = rt.nAlert;
        dto.minDebitPerMin = rt.minDebitPerMin;
        dto.maxDebitPerMin = rt.maxDebitPerMin;
        dto.avgDebitPerMin = rt.avgDebitPerMin;
        dto.rssi           = rt.rssi;
        dto.snr            = rt.snr;
        dto.status = resolveStatus(rt);
        return dto;
    }

    private ArchiveGmDto toArchiveGmDto(ArchiveGm e) {
        ArchiveGmDto dto = new ArchiveGmDto();
        dto.idDevice       = e.id.idDevice;
        dto.date           = e.id.date;
        dto.forwardFlow    = e.forwardFlow;
        dto.reverseFlow    = e.reverseFlow;
        dto.index          = e.index;
        dto.leak           = e.leak;
        dto.fraud          = e.fraud;
        dto.batteryLevel   = e.batteryLevel;
        dto.minDebitPerMin = e.minDebitPerMin;
        dto.maxDebitPerMin = e.maxDebitPerMin;
        dto.avgDebitPerMin = e.avgDebitPerMin;
        return dto;
    }

    private ArchiveGmHDto toArchiveGmHDto(ArchiveGmH e) {
        ArchiveGmHDto dto = new ArchiveGmHDto();
        dto.idDevice       = e.id.idDevice;
        dto.date           = e.id.date;
        dto.conso          = e.conso;
        dto.reverseConso   = e.reverseConso;
        dto.index          = e.index;
        dto.avgDebitPerMin = e.avgDebitPerMin;
        dto.minDebitPerMin = e.minDebitPerMin;
        dto.maxDebitPerMin = e.maxDebitPerMin;
        return dto;
    }

    private ArchiveGmJDto toArchiveGmJDto(ArchiveGmJ e) {
        ArchiveGmJDto dto = new ArchiveGmJDto();
        dto.idDevice       = e.id.idDevice;
        dto.date           = e.id.date;
        dto.conso          = e.conso;
        dto.reverseConso   = e.reverseConso;
        dto.index          = e.index;
        dto.avgDebitPerMin = e.avgDebitPerMin;
        dto.minDebitPerMin = e.minDebitPerMin;
        dto.maxDebitPerMin = e.maxDebitPerMin;
        return dto;
    }

    private ArchiveGmMDto toArchiveGmMDto(ArchiveGmM e) {
        ArchiveGmMDto dto = new ArchiveGmMDto();
        dto.idDevice       = e.id.idDevice;
        dto.date           = e.id.date;
        dto.conso          = e.conso;
        dto.reverseConso   = e.reverseConso;
        dto.index          = e.index;
        dto.avgDebitPerMin = e.avgDebitPerMin;
        return dto;
    }

    private InitGmDto toInitGmDto(InitGm e) {
        InitGmDto dto = new InitGmDto();
        dto.idDevice                  = e.idDevice;
        dto.date                      = e.date;
        dto.consoH                    = e.consoH;
        dto.consoJ                    = e.consoJ;
        dto.consoM                    = e.consoM;
        dto.alertState                = e.alertState;
        dto.highConsumptionCounter    = e.highConsumptionCounter;
        dto.excessiveConsumptionCounter = e.excessiveConsumptionCounter;
        dto.lowConsumptionCounter     = e.lowConsumptionCounter;
        dto.avgDebitPerMin            = e.avgDebitPerMin;
        dto.minDebitPerMin            = e.minDebitPerMin;
        dto.maxDebitPerMin            = e.maxDebitPerMin;
        return dto;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // HELPERS
    // ═══════════════════════════════════════════════════════════════════════════

    private String resolveStatus(RtGm rt) {
        if (rt.leak  != null && rt.leak  == 1) return "LEAK";
        if (rt.fraud != null && rt.fraud == 1) return "FRAUD";
        if (rt.nAlert != null && rt.nAlert > 0) return "ALERT";
        return "OK";
    }

    private double litersToM3(long liters) {
        return liters / (double) LITERS_PER_M3;
    }

    private String computeTrend(Long current, Long previous) {
        double pct = computeVariationPercent(current, previous);
        String sign = pct >= 0 ? "+" : "";
        return sign + String.format("%.1f", pct) + "%";
    }

    private double computeVariationPercent(Long current, Long previous) {
        if (previous == null || previous == 0) return 0.0;
        return ((current - previous) / (double) previous) * 100.0;
    }
}

