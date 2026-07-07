package org.example.service;

import jakarta.enterprise.context.ApplicationScoped;
import org.example.dto.WaterDto;
import org.example.dto.WaterDto.*;
import org.example.entity.*;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Service métier — Module Eau (WM)
 * Facteur CO2 eau : 0.30 kgCO2eq/m³  (énergie traitement + distribution)
 * Tarif eau indicatif : 0.40 TND/m³   (tranche domestique Tunisie)
 * 1 unité conso ≈ 1 litre
 */
@ApplicationScoped
public class WaterService {

    private static final double CO2_FACTOR_PER_M3 = 0.30;   // kgCO2eq / m³
    private static final double COST_PER_M3_TND   = 0.40;   // TND / m³
    private static final int    LITERS_PER_M3      = 1000;

    // ═══════════════════════════════════════════════════════════════════════════
    // TEMPS RÉEL
    // ═══════════════════════════════════════════════════════════════════════════

    public List<RtWmDto> getAllRealTime() {
        return RtWm.findAllActive()
                .stream()
                .map(this::toRtDto)
                .collect(Collectors.toList());
    }

    public RtWmDto getRealTime(Integer idDevice) {
        RtWm rt = RtWm.findByDevice(idDevice);
        if (rt == null) return null;
        return toRtDto(rt);
    }

    public List<RtWmDto> getDevicesWithAlerts() {
        return RtWm.findWithAlerts()
                .stream()
                .map(this::toRtDto)
                .collect(Collectors.toList());
    }

    public List<RtWmDto> getDevicesWithLeak() {
        return RtWm.findWithLeak()
                .stream()
                .map(this::toRtDto)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // BRUT (archive_wm)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ArchiveWmDto> getRawByDeviceAndPeriod(Integer idDevice,
                                                      LocalDateTime from,
                                                      LocalDateTime to) {
        return ArchiveWm.findByDeviceAndPeriod(idDevice, from, to)
                .stream()
                .map(this::toArchiveWmDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveWmDto> getAllRawByPeriod(LocalDateTime from, LocalDateTime to) {
        return ArchiveWm.findAllByPeriod(from, to)
                .stream()
                .map(this::toArchiveWmDto)
                .collect(Collectors.toList());
    }

    public ArchiveWmDto getLatestRaw(Integer idDevice) {
        ArchiveWm raw = ArchiveWm.findLatestByDevice(idDevice);
        if (raw == null) return null;
        return toArchiveWmDto(raw);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // HORAIRE (archive_wm_h)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ArchiveWmHDto> getHourlyByDeviceAndPeriod(Integer idDevice,
                                                          LocalDateTime from,
                                                          LocalDateTime to) {
        return ArchiveWmH.findByDeviceAndPeriod(idDevice, from, to)
                .stream()
                .map(this::toArchiveWmHDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveWmHDto> getAllHourlyByPeriod(LocalDateTime from, LocalDateTime to) {
        return ArchiveWmH.findAllByPeriod(from, to)
                .stream()
                .map(this::toArchiveWmHDto)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // JOURNALIER (archive_wm_j)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ArchiveWmJDto> getDailyByDeviceAndPeriod(Integer idDevice,
                                                         LocalDateTime from,
                                                         LocalDateTime to) {
        return ArchiveWmJ.findByDeviceAndPeriod(idDevice, from, to)
                .stream()
                .map(this::toArchiveWmJDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveWmJDto> getAllDailyByPeriod(LocalDateTime from, LocalDateTime to) {
        return ArchiveWmJ.findAllByPeriod(from, to)
                .stream()
                .map(this::toArchiveWmJDto)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // MENSUEL (archive_wm_m)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ArchiveWmMDto> getMonthlyByDevice(Integer idDevice) {
        return ArchiveWmM.findByDevice(idDevice)
                .stream()
                .map(this::toArchiveWmMDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveWmMDto> getMonthlyByDeviceAndPeriod(Integer idDevice,
                                                           LocalDateTime from,
                                                           LocalDateTime to) {
        return ArchiveWmM.findByDeviceAndPeriod(idDevice, from, to)
                .stream()
                .map(this::toArchiveWmMDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveWmMDto> getAllMonthlyByPeriod(LocalDateTime from, LocalDateTime to) {
        return ArchiveWmM.findAllByPeriod(from, to)
                .stream()
                .map(this::toArchiveWmMDto)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // INIT / CONFIG
    // ═══════════════════════════════════════════════════════════════════════════

    public InitWmDto getConfig(Integer idDevice) {
        InitWm init = InitWm.findByDevice(idDevice);
        if (init == null) return null;
        return toInitWmDto(init);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // RÉSUMÉ / DASHBOARD
    // ═══════════════════════════════════════════════════════════════════════════

    public WaterSummaryDto getSummary(Integer idDevice, LocalDateTime from, LocalDateTime to) {
        RtWm rt = RtWm.findByDevice(idDevice);

        // Recentrer sur la dernière date disponible si la période demandée est vide
        LocalDateTime latestDate = ArchiveWmJ.findLatestDate();
        if (latestDate != null && latestDate.isBefore(from)) {
            long duration = java.time.Duration.between(from, to).toDays();
            to   = latestDate;
            from = to.minusDays(duration);
        }

        // Conso horaire
        Long consoH = ArchiveWmH.totalConsoByDeviceAndPeriod(
                idDevice,
                from.withMinute(0).withSecond(0),
                from.withMinute(59).withSecond(59));

        // Conso journalière et mensuelle sur la période
        Long consoJ = ArchiveWmJ.findByDeviceAndPeriod(idDevice, from, to)
                .stream()
                .mapToLong(r -> r.conso == null ? 0 : r.conso)
                .sum();
        Long consoM = ArchiveWmM.findByDeviceAndPeriod(idDevice, from, to)
                .stream()
                .mapToLong(r -> r.conso == null ? 0 : r.conso)
                .sum();

        // Fallback : si les agrégats sont vides, calculer depuis les données brutes (archive_wm)
        if (consoM == 0 && consoJ == 0) {
            long rawSum = ArchiveWm.findByDeviceAndPeriod(idDevice, from, to)
                    .stream()
                    .mapToLong(r -> r.wmIndex == null ? 0L : r.wmIndex.longValue())
                    .sum();
            consoJ = rawSum;
            consoM = rawSum;
        }

        long bestConso = consoM != 0 ? consoM : consoJ;
        double co2  = litersToM3(bestConso) * CO2_FACTOR_PER_M3;
        double cost = litersToM3(bestConso) * COST_PER_M3_TND;

        int alertCount = (rt != null && rt.nAlert  != null) ? rt.nAlert : 0;
        int leakCount  = (rt != null && rt.leak    != null && rt.leak  == 1) ? 1 : 0;
        int fraudCount = (rt != null && rt.fraud   != null && rt.fraud == 1) ? 1 : 0;

        long duration = java.time.Duration.between(from, to).toDays();
        LocalDateTime prevFrom = from.minusDays(duration);
        Long prevConsoM = ArchiveWmM.findByDeviceAndPeriod(idDevice, prevFrom, from)
                .stream()
                .mapToLong(r -> r.conso == null ? 0 : r.conso)
                .sum();

        WaterSummaryDto dto = new WaterSummaryDto();
        dto.idDevice     = idDevice;
        dto.lastUpdate   = rt != null ? rt.date : null;
        dto.totalConsoH  = consoH;
        dto.totalConsoJ  = consoJ;
        dto.totalConsoM  = consoM;
        dto.totalConsoM3 = Math.round(litersToM3(bestConso) * 100.0) / 100.0;
        dto.alertCount   = alertCount;
        dto.leakCount    = leakCount;
        dto.fraudCount   = fraudCount;
        dto.co2Kg        = Math.round(co2  * 100.0) / 100.0;
        dto.costTnd      = Math.round(cost * 100.0) / 100.0;
        dto.trend        = computeTrend(bestConso, prevConsoM);
        return dto;
    }

    public List<WaterSummaryDto> getAllSummaries(LocalDateTime from, LocalDateTime to) {
        List<RtWm> allRt = RtWm.findAllActive();
        if (allRt.isEmpty()) return List.of();

        long duration = java.time.Duration.between(from, to).toDays();

        // Si la période demandée n'a pas de données, recentrer sur la dernière date disponible
        LocalDateTime latestDate = ArchiveWmJ.findLatestDate();
        if (latestDate != null && latestDate.isBefore(from)) {
            to   = latestDate;
            from = to.minusDays(duration);
        }

        LocalDateTime hFrom    = from.withMinute(0).withSecond(0);
        LocalDateTime hTo      = from.withMinute(59).withSecond(59);
        LocalDateTime prevFrom = from.minusDays(duration);

        // One query per archive table for ALL devices — group in memory
        Map<Integer, Long> consoHMap = ArchiveWmH.findAllByPeriod(hFrom, hTo).stream()
                .collect(Collectors.groupingBy(r -> r.id.idDevice,
                         Collectors.summingLong(r -> r.conso == null ? 0L : r.conso)));

        Map<Integer, Long> consoJMap = ArchiveWmJ.findAllByPeriod(from, to).stream()
                .collect(Collectors.groupingBy(r -> r.id.idDevice,
                         Collectors.summingLong(r -> r.conso == null ? 0L : r.conso)));

        Map<Integer, Long> consoMMap = ArchiveWmM.findAllByPeriod(from, to).stream()
                .collect(Collectors.groupingBy(r -> r.id.idDevice,
                         Collectors.summingLong(r -> r.conso == null ? 0L : r.conso)));

        Map<Integer, Long> prevMMap = ArchiveWmM.findAllByPeriod(prevFrom, from).stream()
                .collect(Collectors.groupingBy(r -> r.id.idDevice,
                         Collectors.summingLong(r -> r.conso == null ? 0L : r.conso)));

        // Raw fallback — only fetch if at least one device has no aggregates
        boolean needsFallback = allRt.stream().anyMatch(rt ->
                consoMMap.getOrDefault(rt.idDevice, 0L) == 0 &&
                consoJMap.getOrDefault(rt.idDevice, 0L) == 0);
        Map<Integer, Long> rawMap = needsFallback
                ? ArchiveWm.findAllByPeriod(from, to).stream()
                        .collect(Collectors.groupingBy(r -> r.id.idDevice,
                                 Collectors.summingLong(r -> r.wmIndex == null ? 0L : r.wmIndex.longValue())))
                : Map.of();

        return allRt.stream().map(rt -> {
            long consoH = consoHMap.getOrDefault(rt.idDevice, 0L);
            long consoJ = consoJMap.getOrDefault(rt.idDevice, 0L);
            long consoM = consoMMap.getOrDefault(rt.idDevice, 0L);

            if (consoM == 0 && consoJ == 0) {
                long raw = rawMap.getOrDefault(rt.idDevice, 0L);
                consoJ = raw;
                consoM = raw;
            }

            // Utiliser consoJ si consoM est absent (données mensuelles manquantes pour la période)
            long bestConso  = consoM != 0 ? consoM : consoJ;
            double co2      = litersToM3(bestConso) * CO2_FACTOR_PER_M3;
            double cost     = litersToM3(bestConso) * COST_PER_M3_TND;
            long prevConsoM = prevMMap.getOrDefault(rt.idDevice, 0L);

            WaterSummaryDto dto = new WaterSummaryDto();
            dto.idDevice     = rt.idDevice;
            dto.lastUpdate   = rt.date;
            dto.totalConsoH  = consoH;
            dto.totalConsoJ  = consoJ;
            dto.totalConsoM  = consoM;
            dto.totalConsoM3 = Math.round(litersToM3(bestConso) * 100.0) / 100.0;
            dto.alertCount   = rt.nAlert != null ? rt.nAlert : 0;
            dto.leakCount    = rt.leak   != null && rt.leak  == 1 ? 1 : 0;
            dto.fraudCount   = rt.fraud  != null && rt.fraud == 1 ? 1 : 0;
            dto.co2Kg        = Math.round(co2  * 100.0) / 100.0;
            dto.costTnd      = Math.round(cost * 100.0) / 100.0;
            dto.trend        = computeTrend(bestConso, prevConsoM);
            return dto;
        }).collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // CHART DATA
    // ═══════════════════════════════════════════════════════════════════════════

    public WaterChartDto getHourlyChart(Integer idDevice, LocalDateTime from, LocalDateTime to) {
        List<ArchiveWmH> records = ArchiveWmH.findByDeviceAndPeriod(idDevice, from, to);

        List<WaterChartPointDto> points = records.stream().map(r -> {
            WaterChartPointDto p = new WaterChartPointDto();
            p.label   = r.id.date.format(DateTimeFormatter.ofPattern("dd/MM HH'h'"));
            p.conso   = r.conso != null ? r.conso : 0;
            p.consoM3 = Math.round(litersToM3(p.conso) * 1000.0) / 1000.0;
            p.co2     = Math.round(litersToM3(p.conso) * CO2_FACTOR_PER_M3 * 100.0) / 100.0;
            p.cost    = Math.round(litersToM3(p.conso) * COST_PER_M3_TND   * 100.0) / 100.0;
            return p;
        }).collect(Collectors.toList());

        return buildChart(points);
    }

    public WaterChartDto getDailyChart(Integer idDevice, LocalDateTime from, LocalDateTime to) {
        List<ArchiveWmJ> records = ArchiveWmJ.findByDeviceAndPeriod(idDevice, from, to);

        List<WaterChartPointDto> points = records.stream().map(r -> {
            WaterChartPointDto p = new WaterChartPointDto();
            p.label   = r.id.date.format(DateTimeFormatter.ofPattern("dd/MM"));
            p.conso   = r.conso != null ? r.conso : 0;
            p.consoM3 = Math.round(litersToM3(p.conso) * 1000.0) / 1000.0;
            p.co2     = Math.round(litersToM3(p.conso) * CO2_FACTOR_PER_M3 * 100.0) / 100.0;
            p.cost    = Math.round(litersToM3(p.conso) * COST_PER_M3_TND   * 100.0) / 100.0;
            return p;
        }).collect(Collectors.toList());

        return buildChart(points);
    }

    public WaterChartDto getMonthlyChart(Integer idDevice, LocalDateTime from, LocalDateTime to) {
        List<ArchiveWmM> records = ArchiveWmM.findByDeviceAndPeriod(idDevice, from, to);

        List<WaterChartPointDto> points = records.stream().map(r -> {
            WaterChartPointDto p = new WaterChartPointDto();
            p.label   = r.id.date.format(DateTimeFormatter.ofPattern("MM/yyyy"));
            p.conso   = r.conso != null ? r.conso : 0;
            p.consoM3 = Math.round(litersToM3(p.conso) * 1000.0) / 1000.0;
            p.co2     = Math.round(litersToM3(p.conso) * CO2_FACTOR_PER_M3 * 100.0) / 100.0;
            p.cost    = Math.round(litersToM3(p.conso) * COST_PER_M3_TND   * 100.0) / 100.0;
            return p;
        }).collect(Collectors.toList());

        return buildChart(points);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // STATISTIQUES AVANCÉES
    // ═══════════════════════════════════════════════════════════════════════════

    public WaterStatsDto getStats(Integer idDevice, LocalDateTime from, LocalDateTime to) {
        List<ArchiveWmJ> dailyRecords = ArchiveWmJ.findByDeviceAndPeriod(idDevice, from, to);
        List<ArchiveWmM> monthlyRecords = ArchiveWmM.findByDeviceAndPeriod(idDevice, from, to);
        RtWm rt = RtWm.findByDevice(idDevice);

        long avgDaily = (long) dailyRecords.stream()
                .mapToLong(r -> r.conso == null ? 0 : r.conso)
                .average()
                .orElse(0);
        long maxDaily = dailyRecords.stream()
                .mapToLong(r -> r.conso == null ? 0 : r.conso)
                .max()
                .orElse(0);
        long minDaily = dailyRecords.stream()
                .mapToLong(r -> r.conso == null ? 0 : r.conso)
                .min()
                .orElse(0);
        long avgMonthly = (long) monthlyRecords.stream()
                .mapToLong(r -> r.conso == null ? 0 : r.conso)
                .average()
                .orElse(0);

        // Comparaison vs mois précédent
        LocalDateTime prevMonthStart = from.minusMonths(1).withDayOfMonth(1).withHour(0).withMinute(0).withSecond(0);
        LocalDateTime prevMonthEnd   = from.withDayOfMonth(1).withHour(0).withMinute(0).withSecond(0);
        Long currentMonthConso  = ArchiveWmM.totalConsoByDeviceAndPeriod(idDevice, from, to);
        Long previousMonthConso = ArchiveWmM.totalConsoByDeviceAndPeriod(idDevice, prevMonthStart, prevMonthEnd);

        WaterStatsDto dto = new WaterStatsDto();
        dto.idDevice             = idDevice;
        dto.avgDailyConsoL       = avgDaily;
        dto.maxDailyConsoL       = maxDaily;
        dto.minDailyConsoL       = minDaily;
        dto.avgMonthlyConsoL     = avgMonthly;
        dto.daysWithLeak         = (rt != null && rt.leak != null && rt.leak == 1) ? 1 : 0;
        dto.totalAlerts          = (rt != null && rt.nAlert != null) ? rt.nAlert : 0;
        dto.variationVsPrevMonth = computeVariationPercent(currentMonthConso, previousMonthConso);
        return dto;
    }

    public List<WaterStatsDto> getAllStats(LocalDateTime from, LocalDateTime to) {
        return RtWm.findAllActive()
                .stream()
                .map(rt -> getStats(rt.idDevice, from, to))
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // ALERTES
    // ═══════════════════════════════════════════════════════════════════════════

    public List<WaterAlertDto> getActiveAlerts() {
        List<WaterAlertDto> alerts = new ArrayList<>();

        RtWm.findWithLeak().forEach(rt -> {
            WaterAlertDto a = new WaterAlertDto();
            a.idDevice = rt.idDevice;
            a.date     = rt.date;
            a.type     = "LEAK";
            a.message  = "Fuite détectée sur le compteur eau " + rt.idDevice;
            a.severity = "CRITICAL";
            alerts.add(a);
        });

        RtWm.findWithFraud().forEach(rt -> {
            WaterAlertDto a = new WaterAlertDto();
            a.idDevice = rt.idDevice;
            a.date     = rt.date;
            a.type     = "FRAUD";
            a.message  = "Tentative de fraude détectée sur le compteur eau " + rt.idDevice;
            a.severity = "CRITICAL";
            alerts.add(a);
        });

        RtWm.findLowBattery().forEach(rt -> {
            WaterAlertDto a = new WaterAlertDto();
            a.idDevice = rt.idDevice;
            a.date     = rt.date;
            a.type     = "LOW_BATTERY";
            a.message  = "Batterie faible (" + rt.batteryLevel + "%) sur compteur eau " + rt.idDevice;
            a.severity = "HIGH";
            alerts.add(a);
        });

        return alerts;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // COMPARAISON PÉRIODES
    // ═══════════════════════════════════════════════════════════════════════════

    public WaterComparisonDto compareWithPreviousPeriod(Integer idDevice,
                                                        LocalDateTime from,
                                                        LocalDateTime to) {
        long duration = java.time.Duration.between(from, to).toDays();
        LocalDateTime prevFrom = from.minusDays(duration);

        Long current  = ArchiveWmJ.findByDeviceAndPeriod(idDevice, from, to)
                .stream().mapToLong(r -> r.conso == null ? 0 : r.conso).sum();
        Long previous = ArchiveWmJ.findByDeviceAndPeriod(idDevice, prevFrom, from)
                .stream().mapToLong(r -> r.conso == null ? 0 : r.conso).sum();

        WaterComparisonDto dto = new WaterComparisonDto();
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

    private RtWmDto toRtDto(RtWm rt) {
        RtWmDto dto = new RtWmDto();
        dto.idDevice     = rt.idDevice;
        dto.date         = rt.date;
        dto.wmIndex      = rt.wmIndex;
        dto.leak         = rt.leak;
        dto.fraud        = rt.fraud;
        dto.batteryLevel = rt.batteryLevel;
        dto.nAlert       = rt.nAlert;
        dto.rssi         = rt.rssi;
        dto.snr          = rt.snr;
        dto.status       = resolveStatus(rt);
        return dto;
    }

    private ArchiveWmDto toArchiveWmDto(ArchiveWm e) {
        ArchiveWmDto dto = new ArchiveWmDto();
        dto.idDevice     = e.id.idDevice;
        dto.date         = e.id.date;
        dto.forwardFlow  = e.forwardFlow;
        dto.reverseFlow  = e.reverseFlow;
        dto.wmIndex      = e.wmIndex;
        dto.leak         = e.leak;
        dto.fraud        = e.fraud;
        dto.batteryLevel = e.batteryLevel;
        dto.rssi         = e.rssi;
        dto.snr          = e.snr;
        return dto;
    }

    private ArchiveWmHDto toArchiveWmHDto(ArchiveWmH e) {
        ArchiveWmHDto dto = new ArchiveWmHDto();
        dto.idDevice     = e.id.idDevice;
        dto.date         = e.id.date;
        dto.conso        = e.conso;
        dto.reverseConso = e.reverseConso;
        dto.wmIndex      = e.wmIndex;
        dto.batteryLevel = e.batteryLevel;
        return dto;
    }

    private ArchiveWmJDto toArchiveWmJDto(ArchiveWmJ e) {
        ArchiveWmJDto dto = new ArchiveWmJDto();
        dto.idDevice     = e.id.idDevice;
        dto.date         = e.id.date;
        dto.conso        = e.conso;
        dto.reverseConso = e.reverseConso;
        dto.wmIndex      = e.wmIndex;
        dto.batteryLevel = e.batteryLevel;
        return dto;
    }

    private ArchiveWmMDto toArchiveWmMDto(ArchiveWmM e) {
        ArchiveWmMDto dto = new ArchiveWmMDto();
        dto.idDevice     = e.id.idDevice;
        dto.date         = e.id.date;
        dto.conso        = e.conso;
        dto.reverseConso = e.reverseConso;
        dto.wmIndex      = e.wmIndex;
        dto.batteryLevel = e.batteryLevel;
        return dto;
    }

    private InitWmDto toInitWmDto(InitWm e) {
        InitWmDto dto = new InitWmDto();
        dto.idDevice                    = e.idDevice;
        dto.date                        = e.date;
        dto.consoH                      = e.consoH;
        dto.consoJ                      = e.consoJ;
        dto.consoM                      = e.consoM;
        dto.reverseConsoH               = e.reverseConsoH;
        dto.reverseConsoJ               = e.reverseConsoJ;
        dto.reverseConsoM               = e.reverseConsoM;
        dto.infractionConsoH            = e.infractionConsoH;
        dto.infractionConsoJ            = e.infractionConsoJ;
        dto.infractionConsoM            = e.infractionConsoM;
        dto.alertState                  = e.alertState;
        dto.highConsumptionCounter      = e.highConsumptionCounter;
        dto.excessiveConsumptionCounter = e.excessiveConsumptionCounter;
        dto.lowConsumptionCounter       = e.lowConsumptionCounter;
        return dto;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // HELPERS
    // ═══════════════════════════════════════════════════════════════════════════

    private WaterChartDto buildChart(List<WaterChartPointDto> points) {
        long   totalL    = points.stream().mapToLong(p -> p.conso).sum();
        double totalM3   = Math.round(litersToM3(totalL) * 1000.0) / 1000.0;
        double totalCo2  = Math.round(litersToM3(totalL) * CO2_FACTOR_PER_M3 * 100.0) / 100.0;
        double totalCost = Math.round(litersToM3(totalL) * COST_PER_M3_TND   * 100.0) / 100.0;

        WaterChartDto chart = new WaterChartDto();
        chart.points      = points;
        chart.totalConsoL = (int) totalL;
        chart.totalConsoM3 = totalM3;
        chart.totalCo2    = totalCo2;
        chart.totalCost   = totalCost;
        return chart;
    }

    private String resolveStatus(RtWm rt) {
        if (rt.leak  != null && rt.leak  == 1) return "LEAK";
        if (rt.fraud != null && rt.fraud == 1) return "FRAUD";
        if (rt.nAlert != null && rt.nAlert > 0) return "ALERT";
        return "OK";
    }

    private double litersToM3(long liters) {
        return liters / (double) LITERS_PER_M3;
    }

    private double litersToM3(Integer liters) {
        if (liters == null) return 0.0;
        return liters / (double) LITERS_PER_M3;
    }

    private String computeTrend(Long current, Long previous) {
        double pct  = computeVariationPercent(current, previous);
        String sign = pct >= 0 ? "+" : "";
        return sign + String.format("%.1f", pct) + "%";
    }

    private double computeVariationPercent(Long current, Long previous) {
        if (previous == null || previous == 0) return 0.0;
        return ((current - previous) / (double) previous) * 100.0;
    }
}
