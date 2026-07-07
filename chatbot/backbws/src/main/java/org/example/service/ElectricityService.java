package org.example.service;

import jakarta.enterprise.context.ApplicationScoped;
import org.example.dto.ElectricityDto;
import org.example.dto.ElectricityDto.*;
import org.example.entity.*;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Service métier — Module Électricité
 *
 * Facteur CO2  : 0.0571 kgCO2/kWh  (réseau tunisien, source STEG/IEA)
 * Tarif        : 0.30 TND/kWh       (tarif indicatif basse tension)
 * Seuil THD   : 5 % (norme EN 50160)
 * Seuil cosfi  : 0.85 (seuil infraction STEG)
 */
@ApplicationScoped
public class ElectricityService {

    // ── Constantes ────────────────────────────────────────────────────────────
    private static final double CO2_FACTOR_KG_PER_KWH = 0.0571;
    private static final double COST_PER_KWH_TND       = 0.30;
    private static final double THD_ALERT_THRESHOLD    = 5.0;   // %
    private static final double COSFI_ALERT_THRESHOLD  = 0.85;

    // ═══════════════════════════════════════════════════════════════════════════
    // TEMPS RÉEL
    // ═══════════════════════════════════════════════════════════════════════════

    public List<RtEnPDto> getAllRealTime() {
        return RtEnP.findAllActive()
                .stream()
                .map(this::toRtDto)
                .collect(Collectors.toList());
    }

    public RtEnPDto getRealTime(Integer idDevice) {
        RtEnP rt = RtEnP.findByDevice(idDevice);
        return rt == null ? null : toRtDto(rt);
    }

    public List<RtEnPDto> getDevicesWithLowBattery() {
        return RtEnP.findLowBattery()
                .stream()
                .map(this::toRtDto)
                .collect(Collectors.toList());
    }

    public List<RtEnPDto> getDevicesWithHighTHD() {
        return RtEnP.findHighTHD(THD_ALERT_THRESHOLD)
                .stream()
                .map(this::toRtDto)
                .collect(Collectors.toList());
    }

    public List<RtEnPDto> getDevicesWithLowCosfi() {
        return RtEnP.findLowCosfi(COSFI_ALERT_THRESHOLD)
                .stream()
                .map(this::toRtDto)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // BRUT (archive_en_p)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ArchiveEnPDto> getRawByDeviceAndPeriod(Integer idDevice,
                                                        LocalDateTime from,
                                                        LocalDateTime to) {
        return ArchiveEnP.findByDeviceAndPeriod(idDevice, from, to)
                .stream()
                .map(this::toArchiveEnPDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveEnPDto> getAllRawByPeriod(LocalDateTime from, LocalDateTime to) {
        return ArchiveEnP.findAllByPeriod(from, to)
                .stream()
                .map(this::toArchiveEnPDto)
                .collect(Collectors.toList());
    }

    public ArchiveEnPDto getLatestRaw(Integer idDevice) {
        ArchiveEnP raw = ArchiveEnP.findLatestByDevice(idDevice);
        return raw == null ? null : toArchiveEnPDto(raw);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // HORAIRE (archive_en_p_h)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ArchiveEnPHDto> getHourlyByDeviceAndPeriod(Integer idDevice,
                                                            LocalDateTime from,
                                                            LocalDateTime to) {
        return ArchiveEnPH.findByDeviceAndPeriod(idDevice, from, to)
                .stream()
                .map(this::toArchiveEnPHDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveEnPHDto> getAllHourlyByPeriod(LocalDateTime from, LocalDateTime to) {
        return ArchiveEnPH.findAllByPeriod(from, to)
                .stream()
                .map(this::toArchiveEnPHDto)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // JOURNALIER (archive_en_p_j)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ArchiveEnPJDto> getDailyByDeviceAndPeriod(Integer idDevice,
                                                           LocalDateTime from,
                                                           LocalDateTime to) {
        return ArchiveEnPJ.findByDeviceAndPeriod(idDevice, from.toLocalDate(), to.toLocalDate())
                .stream()
                .map(this::toArchiveEnPJDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveEnPJDto> getAllDailyByPeriod(LocalDateTime from, LocalDateTime to) {
        return ArchiveEnPJ.findAllByPeriod(from.toLocalDate(), to.toLocalDate())
                .stream()
                .map(this::toArchiveEnPJDto)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // MENSUEL (archive_en_p_m)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ArchiveEnPMDto> getMonthlyByDevice(Integer idDevice) {
        return ArchiveEnPM.findByDevice(idDevice)
                .stream()
                .map(this::toArchiveEnPMDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveEnPMDto> getMonthlyByDeviceAndPeriod(Integer idDevice,
                                                             LocalDateTime from,
                                                             LocalDateTime to) {
        return ArchiveEnPM.findByDeviceAndPeriod(idDevice, from.toLocalDate(), to.toLocalDate())
                .stream()
                .map(this::toArchiveEnPMDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveEnPMDto> getAllMonthlyByPeriod(LocalDateTime from, LocalDateTime to) {
        return ArchiveEnPM.findAllByPeriod(from.toLocalDate(), to.toLocalDate())
                .stream()
                .map(this::toArchiveEnPMDto)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // INIT / CONFIG
    // ═══════════════════════════════════════════════════════════════════════════

    public InitEnergyDto getConfig(Integer idDevice) {
        InitEnergy init = InitEnergy.findByDevice(idDevice);
        return init == null ? null : toInitEnergyDto(init);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // RÉSUMÉ / DASHBOARD
    // ═══════════════════════════════════════════════════════════════════════════

    public ElecSummaryDto getSummary(Integer idDevice, LocalDateTime from, LocalDateTime to) {
        RtEnP rt = RtEnP.findByDevice(idDevice);

        // Consommation horaire (archive_en_p_h pour l'heure courante)
        LocalDateTime hourStart = LocalDateTime.now().withMinute(0).withSecond(0).withNano(0);
        LocalDateTime hourEnd   = hourStart.plusHours(1);
        Double consoH = ArchiveEnPH.totalConsEnByDeviceAndPeriod(idDevice, hourStart, hourEnd);

        // Consommation journalière et mensuelle (archive_en_p_j / archive_en_p_m)
        List<ArchiveEnPJ> daily = ArchiveEnPJ.findByDeviceAndPeriod(
                idDevice, from.toLocalDate(), to.toLocalDate());
        List<ArchiveEnPM> monthly = ArchiveEnPM.findByDeviceAndPeriod(
                idDevice, from.toLocalDate(), to.toLocalDate());

        double consoJ  = daily.stream()
                .mapToDouble(r -> safeDouble(r.consEnL1) + safeDouble(r.consEnL2) + safeDouble(r.consEnL3))
                .sum();
        double consoL1 = daily.stream().mapToDouble(r -> safeDouble(r.consEnL1)).sum();
        double consoL2 = daily.stream().mapToDouble(r -> safeDouble(r.consEnL2)).sum();
        double consoL3 = daily.stream().mapToDouble(r -> safeDouble(r.consEnL3)).sum();

        double consoM  = monthly.stream()
                .mapToDouble(r -> safeDouble(r.consEnL1) + safeDouble(r.consEnL2) + safeDouble(r.consEnL3))
                .sum();

        // Fallback : si les agrégats sont vides, calculer depuis les données brutes (archive_en_p)
        if (consoM == 0 && consoJ == 0) {
            List<ArchiveEnP> raw = ArchiveEnP.findByDeviceAndPeriod(idDevice, from, to);
            consoL1 = raw.stream().mapToDouble(r -> safeDouble(r.enL1)).sum();
            consoL2 = raw.stream().mapToDouble(r -> safeDouble(r.enL2)).sum();
            consoL3 = raw.stream().mapToDouble(r -> safeDouble(r.enL3)).sum();
            consoJ  = consoL1 + consoL2 + consoL3;
            consoM  = consoJ;
        }

        // CO2 et coût : utiliser mensuel si disponible, sinon journalier
        double bestConso = consoM > 0 ? consoM : consoJ;
        double co2  = round2(bestConso * CO2_FACTOR_KG_PER_KWH);
        double cost = round2(bestConso * COST_PER_KWH_TND);

        // Qualité réseau (temps réel)
        double avgCosfi   = rt != null ? (safeDouble(rt.cosfiL1)      + safeDouble(rt.cosfiL2)      + safeDouble(rt.cosfiL3))      / 3.0 : 0.0;
        double avgThd     = rt != null ? (safeDouble(rt.thdL1)        + safeDouble(rt.thdL2)        + safeDouble(rt.thdL3))        / 3.0 : 0.0;
        double avgVoltage = rt != null ? (safeDouble(rt.rmsVoltageL1) + safeDouble(rt.rmsVoltageL2) + safeDouble(rt.rmsVoltageL3)) / 3.0 : 0.0;
        double avgCurrent = rt != null ? (safeDouble(rt.rmsCurrentL1) + safeDouble(rt.rmsCurrentL2) + safeDouble(rt.rmsCurrentL3)) / 3.0 : 0.0;
        double totalPower = rt != null ? (safeDouble(rt.activePowerL1) + safeDouble(rt.activePowerL2) + safeDouble(rt.activePowerL3)) / 1000.0 : 0.0;

        // Alertes
        int alertCount = 0;
        if (rt != null) {
            if (rt.batteryLevel != null && rt.batteryLevel < 50)          alertCount++;
            if (avgThd > THD_ALERT_THRESHOLD)                              alertCount++;
            if (avgCosfi > 0 && avgCosfi < COSFI_ALERT_THRESHOLD)         alertCount++;
        }

        // Tendance vs période précédente (même durée)
        long durationDays = java.time.temporal.ChronoUnit.DAYS.between(from.toLocalDate(), to.toLocalDate());
        LocalDate prevFrom = from.toLocalDate().minusDays(durationDays);
        double prevConsoM = ArchiveEnPM.findByDeviceAndPeriod(idDevice, prevFrom, from.toLocalDate())
                .stream()
                .mapToDouble(r -> safeDouble(r.consEnL1) + safeDouble(r.consEnL2) + safeDouble(r.consEnL3))
                .sum();
        String trend = computeTrend(consoM, prevConsoM);

        ElecSummaryDto dto = new ElecSummaryDto();
        dto.idDevice           = idDevice;
        dto.lastUpdate         = rt != null ? rt.date : null;
        dto.totalConsoHKwh     = round2(consoH != null ? consoH : 0.0);
        dto.totalConsoJKwh     = round2(consoJ);
        dto.totalConsoMKwh     = round2(consoM);
        dto.consoL1Kwh         = round2(consoL1);
        dto.consoL2Kwh         = round2(consoL2);
        dto.consoL3Kwh         = round2(consoL3);
        dto.avgCosfi           = round2(avgCosfi);
        dto.avgThd             = round2(avgThd);
        dto.avgVoltage         = round2(avgVoltage);
        dto.avgCurrent         = round2(avgCurrent);
        dto.totalActivePowerKw = round2(totalPower);
        dto.co2Kg              = co2;
        dto.costTnd            = cost;
        dto.alertCount         = alertCount;
        dto.trend              = trend;
        dto.batteryLevel       = rt != null ? rt.batteryLevel : null;
        dto.status             = resolveStatus(rt);
        return dto;
    }

    public List<ElecSummaryDto> getAllSummaries(LocalDateTime from, LocalDateTime to) {
        return RtEnP.findAllActive()
                .stream()
                .map(rt -> getSummary(rt.idDevice, from, to))
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // CHART DATA
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Chart journalier : un point par jour avec conso, qualité réseau, CO2.
     */
    public ElecChartDto getDailyChart(Integer idDevice, LocalDateTime from, LocalDateTime to) {
        List<ArchiveEnPJ> records = ArchiveEnPJ.findByDeviceAndPeriod(
                idDevice, from.toLocalDate(), to.toLocalDate());

        List<ElecChartPointDto> points = records.stream().map(r -> {
            ElecChartPointDto p = new ElecChartPointDto();
            p.label      = r.date.format(DateTimeFormatter.ofPattern("dd/MM"));
            p.consL1     = safeDouble(r.consEnL1);
            p.consL2     = safeDouble(r.consEnL2);
            p.consL3     = safeDouble(r.consEnL3);
            p.consKwh    = round2(p.consL1 + p.consL2 + p.consL3);
            p.avgCosfi   = round2((safeDouble(r.moyCosfiL1) + safeDouble(r.moyCosfiL2) + safeDouble(r.moyCosfiL3)) / 3.0);
            p.avgThd     = round2((safeDouble(r.moyThdL1)   + safeDouble(r.moyThdL2)   + safeDouble(r.moyThdL3))   / 3.0);
            p.avgVoltage = round2((safeDouble(r.moyRmsVoltageL1) + safeDouble(r.moyRmsVoltageL2) + safeDouble(r.moyRmsVoltageL3)) / 3.0);
            p.co2Kg      = round2(p.consKwh * CO2_FACTOR_KG_PER_KWH);
            return p;
        }).collect(Collectors.toList());

        return buildChart(points);
    }

    /**
     * Chart mensuel : un point par mois avec conso, qualité réseau, CO2.
     */
    public ElecChartDto getMonthlyChart(Integer idDevice, LocalDateTime from, LocalDateTime to) {
        List<ArchiveEnPM> records = ArchiveEnPM.findByDeviceAndPeriod(
                idDevice, from.toLocalDate(), to.toLocalDate());

        List<ElecChartPointDto> points = records.stream().map(r -> {
            ElecChartPointDto p = new ElecChartPointDto();
            p.label      = r.date.format(DateTimeFormatter.ofPattern("MM/yyyy"));
            p.consL1     = safeDouble(r.consEnL1);
            p.consL2     = safeDouble(r.consEnL2);
            p.consL3     = safeDouble(r.consEnL3);
            p.consKwh    = round2(p.consL1 + p.consL2 + p.consL3);
            p.avgCosfi   = round2((safeDouble(r.moyCosfiL1) + safeDouble(r.moyCosfiL2) + safeDouble(r.moyCosfiL3)) / 3.0);
            p.avgThd     = round2((safeDouble(r.moyThdL1)   + safeDouble(r.moyThdL2)   + safeDouble(r.moyThdL3))   / 3.0);
            p.avgVoltage = round2((safeDouble(r.moyRmsVoltageL1) + safeDouble(r.moyRmsVoltageL2) + safeDouble(r.moyRmsVoltageL3)) / 3.0);
            p.co2Kg      = round2(p.consKwh * CO2_FACTOR_KG_PER_KWH);
            return p;
        }).collect(Collectors.toList());

        return buildChart(points);
    }

    /**
     * Chart horaire pour un device sur une plage (N heures).
     */
    public ElecChartDto getHourlyChart(Integer idDevice, LocalDateTime from, LocalDateTime to) {
        List<ArchiveEnPH> records = ArchiveEnPH.findByDeviceAndPeriod(idDevice, from, to);

        List<ElecChartPointDto> points = records.stream().map(r -> {
            ElecChartPointDto p = new ElecChartPointDto();
            p.label      = r.date.format(DateTimeFormatter.ofPattern("dd/MM HH:mm"));
            p.consL1     = safeDouble(r.consEnL1);
            p.consL2     = safeDouble(r.consEnL2);
            p.consL3     = safeDouble(r.consEnL3);
            p.consKwh    = round2(p.consL1 + p.consL2 + p.consL3);
            p.avgCosfi   = round2((safeDouble(r.moyCosfiL1) + safeDouble(r.moyCosfiL2) + safeDouble(r.moyCosfiL3)) / 3.0);
            p.avgThd     = round2((safeDouble(r.moyThdL1)   + safeDouble(r.moyThdL2)   + safeDouble(r.moyThdL3))   / 3.0);
            p.avgVoltage = round2((safeDouble(r.moyRmsVoltageL1) + safeDouble(r.moyRmsVoltageL2) + safeDouble(r.moyRmsVoltageL3)) / 3.0);
            p.co2Kg      = round2(p.consKwh * CO2_FACTOR_KG_PER_KWH);
            return p;
        }).collect(Collectors.toList());

        return buildChart(points);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // QUALITÉ RÉSEAU
    // ═══════════════════════════════════════════════════════════════════════════

    public List<PowerQualityDto> getPowerQualityDaily(Integer idDevice, LocalDateTime from, LocalDateTime to) {
        return ArchiveEnPJ.findByDeviceAndPeriod(idDevice, from.toLocalDate(), to.toLocalDate())
                .stream()
                .map(this::toPowerQualityDto)
                .collect(Collectors.toList());
    }

    public List<PowerQualityDto> getPowerQualityMonthly(Integer idDevice, LocalDateTime from, LocalDateTime to) {
        return ArchiveEnPM.findByDeviceAndPeriod(idDevice, from.toLocalDate(), to.toLocalDate())
                .stream()
                .map(this::toPowerQualityFromMonthly)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // ALERTES
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ElecAlertDto> getActiveAlerts() {
        List<ElecAlertDto> alerts = new ArrayList<>();

        // Batterie faible
        RtEnP.findLowBattery().forEach(rt -> {
            ElecAlertDto a = new ElecAlertDto();
            a.idDevice = rt.idDevice;
            a.date     = rt.date;
            a.type     = "LOW_BATTERY";
            a.message  = "Batterie faible (" + rt.batteryLevel + "%) — compteur " + rt.idDevice;
            a.severity = "HIGH";
            a.value    = rt.batteryLevel != null ? rt.batteryLevel.doubleValue() : 0.0;
            alerts.add(a);
        });

        // THD élevé
        RtEnP.findHighTHD(THD_ALERT_THRESHOLD).forEach(rt -> {
            double maxThd = Math.max(Math.max(safeDouble(rt.thdL1), safeDouble(rt.thdL2)), safeDouble(rt.thdL3));
            ElecAlertDto a = new ElecAlertDto();
            a.idDevice = rt.idDevice;
            a.date     = rt.date;
            a.type     = "HIGH_THD";
            a.message  = String.format("THD élevé (%.2f%%) — compteur %d", maxThd, rt.idDevice);
            a.severity = maxThd > 10.0 ? "CRITICAL" : "HIGH";
            a.value    = maxThd;
            alerts.add(a);
        });

        // Cosfi faible
        RtEnP.findLowCosfi(COSFI_ALERT_THRESHOLD).forEach(rt -> {
            double minCosfi = Math.min(Math.min(
                    rt.cosfiL1 != null && rt.cosfiL1 > 0 ? rt.cosfiL1 : 1.0,
                    rt.cosfiL2 != null && rt.cosfiL2 > 0 ? rt.cosfiL2 : 1.0),
                    rt.cosfiL3 != null && rt.cosfiL3 > 0 ? rt.cosfiL3 : 1.0);
            ElecAlertDto a = new ElecAlertDto();
            a.idDevice = rt.idDevice;
            a.date     = rt.date;
            a.type     = "LOW_COSFI";
            a.message  = String.format("Facteur de puissance faible (%.3f) — compteur %d", minCosfi, rt.idDevice);
            a.severity = minCosfi < 0.7 ? "CRITICAL" : "HIGH";
            a.value    = minCosfi;
            alerts.add(a);
        });

        return alerts;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // COMPARAISON PÉRIODES
    // ═══════════════════════════════════════════════════════════════════════════

    public ElecComparisonDto compareWithPreviousPeriod(Integer idDevice,
                                                        LocalDateTime from,
                                                        LocalDateTime to) {
        long durationDays = java.time.temporal.ChronoUnit.DAYS.between(from.toLocalDate(), to.toLocalDate());
        LocalDate prevFrom = from.toLocalDate().minusDays(durationDays);

        double current = ArchiveEnPJ.findByDeviceAndPeriod(idDevice, from.toLocalDate(), to.toLocalDate())
                .stream()
                .mapToDouble(r -> safeDouble(r.consEnL1) + safeDouble(r.consEnL2) + safeDouble(r.consEnL3))
                .sum();

        double previous = ArchiveEnPJ.findByDeviceAndPeriod(idDevice, prevFrom, from.toLocalDate())
                .stream()
                .mapToDouble(r -> safeDouble(r.consEnL1) + safeDouble(r.consEnL2) + safeDouble(r.consEnL3))
                .sum();

        double variationPct = computeVariationPercent(current, previous);

        ElecComparisonDto dto = new ElecComparisonDto();
        dto.currentPeriodKwh  = round2(current);
        dto.previousPeriodKwh = round2(previous);
        dto.variationPercent  = round2(variationPct);
        dto.trend = variationPct > 2 ? "UP" : variationPct < -2 ? "DOWN" : "STABLE";
        dto.currentCo2Kg      = round2(current  * CO2_FACTOR_KG_PER_KWH);
        dto.previousCo2Kg     = round2(previous * CO2_FACTOR_KG_PER_KWH);
        dto.currentCostTnd    = round2(current  * COST_PER_KWH_TND);
        dto.previousCostTnd   = round2(previous * COST_PER_KWH_TND);
        return dto;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // MAPPERS PRIVÉS
    // ═══════════════════════════════════════════════════════════════════════════

    private RtEnPDto toRtDto(RtEnP rt) {
        RtEnPDto dto = new RtEnPDto();
        dto.idDevice             = rt.idDevice;
        dto.date                 = rt.date;
        dto.enL1                 = rt.enL1;
        dto.enL2                 = rt.enL2;
        dto.enL3                 = rt.enL3;
        dto.cosfiL1              = rt.cosfiL1;
        dto.cosfiL2              = rt.cosfiL2;
        dto.cosfiL3              = rt.cosfiL3;
        dto.thdL1                = rt.thdL1;
        dto.thdL2                = rt.thdL2;
        dto.thdL3                = rt.thdL3;
        dto.thdcL1               = rt.thdcL1;
        dto.thdcL2               = rt.thdcL2;
        dto.thdcL3               = rt.thdcL3;
        dto.rmsCurrentL1         = rt.rmsCurrentL1;
        dto.rmsCurrentL2         = rt.rmsCurrentL2;
        dto.rmsCurrentL3         = rt.rmsCurrentL3;
        dto.rmsVoltageL1         = rt.rmsVoltageL1;
        dto.rmsVoltageL2         = rt.rmsVoltageL2;
        dto.rmsVoltageL3         = rt.rmsVoltageL3;
        dto.activePowerL1        = rt.activePowerL1;
        dto.activePowerL2        = rt.activePowerL2;
        dto.activePowerL3        = rt.activePowerL3;
        dto.enReactiveL1         = rt.enReactiveL1;
        dto.enReactiveL2         = rt.enReactiveL2;
        dto.enReactiveL3         = rt.enReactiveL3;
        dto.enApparentL1         = rt.enApparentL1;
        dto.enApparentL2         = rt.enApparentL2;
        dto.enApparentL3         = rt.enApparentL3;
        dto.enAccumuleeJourL1    = rt.enAccumuleeJourL1;
        dto.enAccumuleeJourL2    = rt.enAccumuleeJourL2;
        dto.enAccumuleeJourL3    = rt.enAccumuleeJourL3;
        dto.enAccumuleeMoisL1    = rt.enAccumuleeMoisL1;
        dto.enAccumuleeMoisL2    = rt.enAccumuleeMoisL2;
        dto.enAccumuleeMoisL3    = rt.enAccumuleeMoisL3;
        dto.rssi                 = rt.rssi;
        dto.snr                  = rt.snr;
        dto.batteryLevel         = rt.batteryLevel;
        dto.status               = resolveStatus(rt);
        return dto;
    }

    private ArchiveEnPDto toArchiveEnPDto(ArchiveEnP e) {
        ArchiveEnPDto dto = new ArchiveEnPDto();
        dto.idDevice      = e.idDevice;
        dto.date          = e.date;
        dto.enL1          = e.enL1;
        dto.enL2          = e.enL2;
        dto.enL3          = e.enL3;
        dto.cosfiL1       = e.cosfiL1;
        dto.cosfiL2       = e.cosfiL2;
        dto.cosfiL3       = e.cosfiL3;
        dto.thdL1         = e.thdL1;
        dto.thdL2         = e.thdL2;
        dto.thdL3         = e.thdL3;
        dto.thdcL1        = e.thdcL1;
        dto.thdcL2        = e.thdcL2;
        dto.thdcL3        = e.thdcL3;
        dto.rmsCurrentL1  = e.rmsCurrentL1;
        dto.rmsCurrentL2  = e.rmsCurrentL2;
        dto.rmsCurrentL3  = e.rmsCurrentL3;
        dto.rmsVoltageL1  = e.rmsVoltageL1;
        dto.rmsVoltageL2  = e.rmsVoltageL2;
        dto.rmsVoltageL3  = e.rmsVoltageL3;
        dto.activePowerL1 = e.activePowerL1;
        dto.activePowerL2 = e.activePowerL2;
        dto.activePowerL3 = e.activePowerL3;
        dto.enReactiveL1  = e.enReactiveL1;
        dto.enReactiveL2  = e.enReactiveL2;
        dto.enReactiveL3  = e.enReactiveL3;
        dto.batteryLevel  = e.batteryLevel;
        dto.rssi          = e.rssi;
        dto.snr           = e.snr;
        return dto;
    }

    private ArchiveEnPHDto toArchiveEnPHDto(ArchiveEnPH e) {
        ArchiveEnPHDto dto = new ArchiveEnPHDto();
        dto.idDevice          = e.idDevice;
        dto.date              = e.date;
        dto.consEnL1          = e.consEnL1;
        dto.consEnL2          = e.consEnL2;
        dto.consEnL3          = e.consEnL3;
        dto.totalConsKwh      = round2(safeDouble(e.consEnL1) + safeDouble(e.consEnL2) + safeDouble(e.consEnL3));
        dto.enL1              = e.enL1;
        dto.enL2              = e.enL2;
        dto.enL3              = e.enL3;
        dto.moyCosfiL1        = e.moyCosfiL1;
        dto.moyCosfiL2        = e.moyCosfiL2;
        dto.moyCosfiL3        = e.moyCosfiL3;
        dto.moyThdL1          = e.moyThdL1;
        dto.moyThdL2          = e.moyThdL2;
        dto.moyThdL3          = e.moyThdL3;
        dto.moyRmsVoltageL1   = e.moyRmsVoltageL1;
        dto.moyRmsVoltageL2   = e.moyRmsVoltageL2;
        dto.moyRmsVoltageL3   = e.moyRmsVoltageL3;
        dto.moyRmsCurrentL1   = e.moyRmsCurrentL1;
        dto.moyRmsCurrentL2   = e.moyRmsCurrentL2;
        dto.moyRmsCurrentL3   = e.moyRmsCurrentL3;
        dto.moyActivePowerL1  = e.moyActivePowerL1;
        dto.moyActivePowerL2  = e.moyActivePowerL2;
        dto.moyActivePowerL3  = e.moyActivePowerL3;
        dto.consEnReactiveL1  = e.consEnReactiveL1;
        dto.consEnReactiveL2  = e.consEnReactiveL2;
        dto.consEnReactiveL3  = e.consEnReactiveL3;
        dto.consEnApparentL1  = e.consEnApparentL1;
        dto.consEnApparentL2  = e.consEnApparentL2;
        dto.consEnApparentL3  = e.consEnApparentL3;
        dto.batteryLevel      = e.batteryLevel;
        return dto;
    }

    private ArchiveEnPJDto toArchiveEnPJDto(ArchiveEnPJ e) {
        ArchiveEnPJDto dto = new ArchiveEnPJDto();
        dto.idDevice          = e.idDevice;
        dto.date              = e.date;
        dto.consEnL1          = e.consEnL1;
        dto.consEnL2          = e.consEnL2;
        dto.consEnL3          = e.consEnL3;
        dto.totalConsKwh      = round2(safeDouble(e.consEnL1) + safeDouble(e.consEnL2) + safeDouble(e.consEnL3));
        dto.enL1              = e.enL1;
        dto.enL2              = e.enL2;
        dto.enL3              = e.enL3;
        dto.moyCosfiL1        = e.moyCosfiL1;
        dto.moyCosfiL2        = e.moyCosfiL2;
        dto.moyCosfiL3        = e.moyCosfiL3;
        dto.minCosfiL1        = e.minCosfiL1;
        dto.minCosfiL2        = e.minCosfiL2;
        dto.minCosfiL3        = e.minCosfiL3;
        dto.moyThdL1          = e.moyThdL1;
        dto.moyThdL2          = e.moyThdL2;
        dto.moyThdL3          = e.moyThdL3;
        dto.maxThdL1          = e.maxThdL1;
        dto.maxThdL2          = e.maxThdL2;
        dto.maxThdL3          = e.maxThdL3;
        dto.moyRmsVoltageL1   = e.moyRmsVoltageL1;
        dto.moyRmsVoltageL2   = e.moyRmsVoltageL2;
        dto.moyRmsVoltageL3   = e.moyRmsVoltageL3;
        dto.minRmsVoltageL1   = e.minRmsVoltageL1;
        dto.maxRmsVoltageL1   = e.maxRmsVoltageL1;
        dto.moyRmsCurrentL1   = e.moyRmsCurrentL1;
        dto.moyRmsCurrentL2   = e.moyRmsCurrentL2;
        dto.moyRmsCurrentL3   = e.moyRmsCurrentL3;
        dto.moyActivePowerL1  = e.moyActivePowerL1;
        dto.moyActivePowerL2  = e.moyActivePowerL2;
        dto.moyActivePowerL3  = e.moyActivePowerL3;
        dto.consEnReactiveL1  = e.consEnReactiveL1;
        dto.consEnReactiveL2  = e.consEnReactiveL2;
        dto.consEnReactiveL3  = e.consEnReactiveL3;
        dto.consEnApparentL1  = e.consEnApparentL1;
        dto.consEnApparentL2  = e.consEnApparentL2;
        dto.consEnApparentL3  = e.consEnApparentL3;
        dto.batteryLevel      = e.batteryLevel;
        return dto;
    }

    private ArchiveEnPMDto toArchiveEnPMDto(ArchiveEnPM e) {
        ArchiveEnPMDto dto = new ArchiveEnPMDto();
        dto.idDevice          = e.idDevice;
        dto.date              = e.date;
        dto.consEnL1          = e.consEnL1;
        dto.consEnL2          = e.consEnL2;
        dto.consEnL3          = e.consEnL3;
        dto.totalConsKwh      = round2(safeDouble(e.consEnL1) + safeDouble(e.consEnL2) + safeDouble(e.consEnL3));
        dto.enL1              = e.enL1;
        dto.enL2              = e.enL2;
        dto.enL3              = e.enL3;
        dto.moyCosfiL1        = e.moyCosfiL1;
        dto.moyCosfiL2        = e.moyCosfiL2;
        dto.moyCosfiL3        = e.moyCosfiL3;
        dto.moyThdL1          = e.moyThdL1;
        dto.moyThdL2          = e.moyThdL2;
        dto.moyThdL3          = e.moyThdL3;
        dto.moyRmsVoltageL1   = e.moyRmsVoltageL1;
        dto.moyRmsVoltageL2   = e.moyRmsVoltageL2;
        dto.moyRmsVoltageL3   = e.moyRmsVoltageL3;
        dto.moyRmsCurrentL1   = e.moyRmsCurrentL1;
        dto.moyRmsCurrentL2   = e.moyRmsCurrentL2;
        dto.moyRmsCurrentL3   = e.moyRmsCurrentL3;
        dto.moyActivePowerL1  = e.moyActivePowerL1;
        dto.moyActivePowerL2  = e.moyActivePowerL2;
        dto.moyActivePowerL3  = e.moyActivePowerL3;
        dto.consEnReactiveL1  = e.consEnReactiveL1;
        dto.consEnReactiveL2  = e.consEnReactiveL2;
        dto.consEnReactiveL3  = e.consEnReactiveL3;
        dto.batteryLevel      = e.batteryLevel;
        return dto;
    }

    private InitEnergyDto toInitEnergyDto(InitEnergy e) {
        InitEnergyDto dto = new InitEnergyDto();
        dto.idDevice                    = e.idDevice;
        dto.date                        = e.date;
        dto.enL1                        = e.enL1;
        dto.enL2                        = e.enL2;
        dto.enL3                        = e.enL3;
        dto.consHrEnL1                  = e.consHrEnL1;
        dto.consHrEnL2                  = e.consHrEnL2;
        dto.consHrEnL3                  = e.consHrEnL3;
        dto.consJrEnL1                  = e.consJrEnL1;
        dto.consJrEnL2                  = e.consJrEnL2;
        dto.consJrEnL3                  = e.consJrEnL3;
        dto.consMEnL1                   = e.consMEnL1;
        dto.consMEnL2                   = e.consMEnL2;
        dto.consMEnL3                   = e.consMEnL3;
        dto.cosfiL1                     = e.cosfiL1;
        dto.cosfiL2                     = e.cosfiL2;
        dto.cosfiL3                     = e.cosfiL3;
        dto.alertState                  = e.alertState;
        dto.highConsumptionCounter      = e.highConsumptionCounter;
        dto.excessiveConsumptionCounter = e.excessiveConsumptionCounter;
        dto.lowConsumptionCounter       = e.lowConsumptionCounter;
        dto.infractionCosfiL1           = e.infractionCosfiL1;
        dto.infractionCosfiL2           = e.infractionCosfiL2;
        dto.infractionCosfiL3           = e.infractionCosfiL3;
        dto.infractionThdL1             = e.infractionThdL1;
        dto.infractionThdL2             = e.infractionThdL2;
        dto.infractionThdL3             = e.infractionThdL3;
        dto.batteryLevel                = e.batteryLevel;
        dto.rssi                        = e.rssi;
        dto.snr                         = e.snr;
        return dto;
    }

    private PowerQualityDto toPowerQualityDto(ArchiveEnPJ e) {
        PowerQualityDto dto = new PowerQualityDto();
        dto.idDevice     = e.idDevice;
        dto.date         = e.date;
        dto.moyCosfiL1   = e.moyCosfiL1;
        dto.moyCosfiL2   = e.moyCosfiL2;
        dto.moyCosfiL3   = e.moyCosfiL3;
        dto.moyThdL1     = e.moyThdL1;
        dto.moyThdL2     = e.moyThdL2;
        dto.moyThdL3     = e.moyThdL3;
        dto.moyThdcL1    = e.moyThdcL1;
        dto.moyThdcL2    = e.moyThdcL2;
        dto.moyThdcL3    = e.moyThdcL3;
        dto.moyVoltageL1 = e.moyRmsVoltageL1;
        dto.moyVoltageL2 = e.moyRmsVoltageL2;
        dto.moyVoltageL3 = e.moyRmsVoltageL3;
        dto.moyCurrentL1 = e.moyRmsCurrentL1;
        dto.moyCurrentL2 = e.moyRmsCurrentL2;
        dto.moyCurrentL3 = e.moyRmsCurrentL3;
        return dto;
    }

    private PowerQualityDto toPowerQualityFromMonthly(ArchiveEnPM e) {
        PowerQualityDto dto = new PowerQualityDto();
        dto.idDevice     = e.idDevice;
        dto.date         = e.date;
        dto.moyCosfiL1   = e.moyCosfiL1;
        dto.moyCosfiL2   = e.moyCosfiL2;
        dto.moyCosfiL3   = e.moyCosfiL3;
        dto.moyThdL1     = e.moyThdL1;
        dto.moyThdL2     = e.moyThdL2;
        dto.moyThdL3     = e.moyThdL3;
        dto.moyThdcL1    = e.moyThdcL1;
        dto.moyThdcL2    = e.moyThdcL2;
        dto.moyThdcL3    = e.moyThdcL3;
        dto.moyVoltageL1 = e.moyRmsVoltageL1;
        dto.moyVoltageL2 = e.moyRmsVoltageL2;
        dto.moyVoltageL3 = e.moyRmsVoltageL3;
        dto.moyCurrentL1 = e.moyRmsCurrentL1;
        dto.moyCurrentL2 = e.moyRmsCurrentL2;
        dto.moyCurrentL3 = e.moyRmsCurrentL3;
        return dto;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // HELPERS
    // ═══════════════════════════════════════════════════════════════════════════

    private String resolveStatus(RtEnP rt) {
        if (rt == null) return "UNKNOWN";
        if (rt.batteryLevel != null && rt.batteryLevel < 50) return "LOW_BATTERY";
        double avgThd = (safeDouble(rt.thdL1) + safeDouble(rt.thdL2) + safeDouble(rt.thdL3)) / 3.0;
        if (avgThd > THD_ALERT_THRESHOLD) return "HIGH_THD";
        double avgCosfi = (safeDouble(rt.cosfiL1) + safeDouble(rt.cosfiL2) + safeDouble(rt.cosfiL3)) / 3.0;
        if (avgCosfi > 0 && avgCosfi < COSFI_ALERT_THRESHOLD) return "LOW_COSFI";
        return "OK";
    }

    private ElecChartDto buildChart(List<ElecChartPointDto> points) {
        double totalCons = points.stream().mapToDouble(p -> p.consKwh != null ? p.consKwh : 0.0).sum();
        ElecChartDto chart = new ElecChartDto();
        chart.points       = points;
        chart.totalConsKwh = round2(totalCons);
        chart.totalCo2Kg   = round2(totalCons * CO2_FACTOR_KG_PER_KWH);
        chart.totalCostTnd = round2(totalCons * COST_PER_KWH_TND);
        return chart;
    }

    private double safeDouble(Double v) {
        return v != null ? v : 0.0;
    }

    private double round2(double v) {
        return Math.round(v * 100.0) / 100.0;
    }

    private String computeTrend(double current, double previous) {
        double pct = computeVariationPercent(current, previous);
        String sign = pct >= 0 ? "+" : "";
        return sign + String.format("%.1f", pct) + "%";
    }

    private double computeVariationPercent(double current, double previous) {
        if (previous == 0) return 0.0;
        return ((current - previous) / previous) * 100.0;
    }
}
