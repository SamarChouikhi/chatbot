package org.example.service;

import jakarta.enterprise.context.ApplicationScoped;
import org.example.dto.FuelDto.*;
import org.example.entity.*;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Service métier — Module Carburant (Fuel)
 *
 * CO₂ Diesel  : 2.68 kgCO₂eq/L  (ADEME référence France/Tunisie)
 * Prix diesel : 1.89 TND/L       (tarif Tunisie 2025, indicatif)
 * Seuil alerte HIGH_CONSO    : consommation journalière > 120 L
 * Seuil alerte LOW_EFFICIENCY : rendement > 15 L/100km
 * Seuil alerte EXCESSIVE_IDLE : temps_arret > 120 min/jour
 * Seuil alerte HIGH_SPEED     : vitesse moy > 100 km/h
 */
@ApplicationScoped
public class FuelService {

    private static final double CO2_PER_LITER        = 2.68;   // kgCO2eq/L diesel
    private static final double COST_PER_LITER_TND   = 1.89;   // TND/L
    private static final double ALERT_HIGH_CONSO_L   = 120.0;  // L/jour
    private static final double ALERT_LOW_EFF_L100KM = 15.0;   // L/100km
    private static final double ALERT_IDLE_MIN        = 120.0;  // minutes
    // Seuil alerte HIGH_SPEED réservé pour usage futur (non levée actuellement)

    // ═══════════════════════════════════════════════════════════════════════════
    // DERNIER ÉTAT (fuel_consumption latest)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<FuelLatestDto> getAllLatest() {
        return FuelConsumption.findActiveDevices().stream()
                .map(this::getLatest)
                .filter(d -> d != null)
                .collect(Collectors.toList());
    }

    public FuelLatestDto getLatest(Integer deviceId) {
        FuelConsumption fc = FuelConsumption.findLatestByDevice(deviceId);
        if (fc == null) return null;
        return toLatestDto(fc);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // BRUT (archive_fuel)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ArchiveFuelDto> getRawByDeviceAndPeriod(
            Integer idDevice, LocalDateTime from, LocalDateTime to) {
        return ArchiveFuel.findByDeviceAndPeriod(idDevice, from, to).stream()
                .map(this::toArchiveFuelDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveFuelDto> getAllRawByPeriod(LocalDateTime from, LocalDateTime to) {
        return ArchiveFuel.findAllByPeriod(from, to).stream()
                .map(this::toArchiveFuelDto)
                .collect(Collectors.toList());
    }

    public ArchiveFuelDto getLatestRaw(Integer idDevice) {
        ArchiveFuel e = ArchiveFuel.findLatestByDevice(idDevice);
        return e != null ? toArchiveFuelDto(e) : null;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // HORAIRE (archive_fuel_h)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ArchiveFuelHDto> getHourlyByDeviceAndPeriod(
            Integer idDevice, LocalDateTime from, LocalDateTime to) {
        return ArchiveFuelH.findByDeviceAndPeriod(idDevice, from, to).stream()
                .map(this::toArchiveFuelHDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveFuelHDto> getAllHourlyByPeriod(LocalDateTime from, LocalDateTime to) {
        return ArchiveFuelH.findAllByPeriod(from, to).stream()
                .map(this::toArchiveFuelHDto)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // JOURNALIER (archive_fuel_j)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ArchiveFuelJDto> getDailyByDeviceAndPeriod(
            Integer idDevice, LocalDateTime from, LocalDateTime to) {
        return ArchiveFuelJ.findByDeviceAndPeriod(idDevice, from, to).stream()
                .map(this::toArchiveFuelJDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveFuelJDto> getAllDailyByPeriod(LocalDateTime from, LocalDateTime to) {
        return ArchiveFuelJ.findAllByPeriod(from, to).stream()
                .map(this::toArchiveFuelJDto)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // MENSUEL (archive_fuel_m)
    // ═══════════════════════════════════════════════════════════════════════════

    public List<ArchiveFuelMDto> getMonthlyByDevice(Integer idDevice) {
        return ArchiveFuelM.findByDevice(idDevice).stream()
                .map(this::toArchiveFuelMDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveFuelMDto> getMonthlyByDeviceAndPeriod(
            Integer idDevice, LocalDateTime from, LocalDateTime to) {
        return ArchiveFuelM.findByDeviceAndPeriod(idDevice, from, to).stream()
                .map(this::toArchiveFuelMDto)
                .collect(Collectors.toList());
    }

    public List<ArchiveFuelMDto> getAllMonthlyByPeriod(LocalDateTime from, LocalDateTime to) {
        return ArchiveFuelM.findAllByPeriod(from, to).stream()
                .map(this::toArchiveFuelMDto)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // fuel_consumption enrichi
    // ═══════════════════════════════════════════════════════════════════════════

    public List<FuelConsumptionDto> getConsumptionByDevice(Integer deviceId) {
        return FuelConsumption.findByDevice(deviceId).stream()
                .map(this::toFuelConsumptionDto)
                .collect(Collectors.toList());
    }

    public List<FuelConsumptionDto> getConsumptionByPeriod(LocalDateTime from, LocalDateTime to) {
        return FuelConsumption.findAllByPeriod(from, to).stream()
                .map(this::toFuelConsumptionDto)
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // RÉSUMÉ / DASHBOARD
    // ═══════════════════════════════════════════════════════════════════════════

    public FuelSummaryDto getSummary(Integer deviceId, LocalDateTime from, LocalDateTime to) {
        long duration = java.time.Duration.between(from, to).toDays();
        LocalDateTime latestDate = FuelConsumption.findLatestDate();
        if (latestDate != null && latestDate.isBefore(from)) {
            to   = latestDate;
            from = to.minusDays(duration);
        }

        List<FuelConsumption> records = FuelConsumption.findByDeviceAndPeriod(deviceId, from, to);
        FuelConsumption       latest  = FuelConsumption.findLatestByDevice(deviceId);

        double totalConsoL    = records.stream()
                .mapToDouble(r -> r.consumptionLiters != null ? r.consumptionLiters.doubleValue() : 0.0)
                .sum();
        double totalDistanceKm = ArchiveFuelJ.totalDistanceByDeviceAndPeriod(deviceId, from, to);
        double totalCo2        = round2(totalConsoL * CO2_PER_LITER);
        double totalCost       = records.stream()
                .mapToDouble(r -> r.cost != null ? r.cost.doubleValue() : 0.0)
                .sum();

        double avgSpeed = ArchiveFuelJ.findByDeviceAndPeriod(deviceId, from, to).stream()
                .mapToDouble(j -> j.vitesse != null ? j.vitesse : 0.0)
                .average()
                .orElse(0.0);

        double efficiency = totalDistanceKm > 0
                ? round2((totalConsoL / totalDistanceKm) * 100.0)
                : 0.0;

        // Tendance vs période précédente
        long   days     = java.time.Duration.between(from, to).toDays();
        LocalDateTime prevFrom = from.minusDays(days);
        double prevConsoL = FuelConsumption.findByDeviceAndPeriod(deviceId, prevFrom, from).stream()
                .mapToDouble(r -> r.consumptionLiters != null ? r.consumptionLiters.doubleValue() : 0.0)
                .sum();

        FuelSummaryDto dto = new FuelSummaryDto();
        dto.deviceId             = deviceId;
        dto.lastUpdate           = latest != null ? latest.id.date : null;
        dto.totalConsoL          = round2(totalConsoL);
        dto.totalDistanceKm      = round2(totalDistanceKm);
        dto.avgSpeedKmh          = round2(avgSpeed);
        dto.avgEfficiencyL100km  = efficiency;
        dto.co2Kg                = totalCo2;
        dto.costTnd              = round2(totalCost > 0 ? totalCost : totalConsoL * COST_PER_LITER_TND);
        dto.fuelType             = latest != null ? latest.fuelType : "Diesel";
        dto.trend                = computeTrend(totalConsoL, prevConsoL);
        dto.alertCount           = countAlertsForDevice(deviceId, from, to);
        return dto;
    }

    public List<FuelSummaryDto> getAllSummaries(LocalDateTime from, LocalDateTime to) {
        List<Integer> devices = FuelConsumption.findActiveDevices();
        if (devices.isEmpty()) return List.of();

        long duration = java.time.Duration.between(from, to).toDays();
        LocalDateTime latestDate = FuelConsumption.findLatestDate();
        if (latestDate != null && latestDate.isBefore(from)) {
            to   = latestDate;
            from = to.minusDays(duration);
        }

        final LocalDateTime finalFrom = from;
        final LocalDateTime finalTo   = to;
        return devices.stream()
                .map(d -> getSummary(d, finalFrom, finalTo))
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // CHART DATA
    // ═══════════════════════════════════════════════════════════════════════════

    public FuelChartDto getDailyChart(Integer deviceId, LocalDateTime from, LocalDateTime to) {
        List<ArchiveFuelJ> records = ArchiveFuelJ.findByDeviceAndPeriod(deviceId, from, to);

        List<FuelChartPointDto> points = records.stream().map(r -> {
            FuelChartPointDto p = new FuelChartPointDto();
            p.label    = r.date.format(DateTimeFormatter.ofPattern("dd/MM"));
            p.conso    = r.consommation != null ? round2(r.consommation) : 0.0;
            p.distance = r.distance    != null ? round2(r.distance)    : 0.0;
            p.co2      = round2(p.conso * CO2_PER_LITER);
            p.cost     = round2(p.conso * COST_PER_LITER_TND);
            p.efficiency = p.distance > 0 ? round2((p.conso / p.distance) * 100.0) : 0.0;
            return p;
        }).collect(Collectors.toList());

        return buildChart(points);
    }

    public FuelChartDto getMonthlyChart(Integer deviceId, LocalDateTime from, LocalDateTime to) {
        List<ArchiveFuelM> records = ArchiveFuelM.findByDeviceAndPeriod(deviceId, from, to);

        List<FuelChartPointDto> points = records.stream().map(r -> {
            FuelChartPointDto p = new FuelChartPointDto();
            p.label    = r.date.format(DateTimeFormatter.ofPattern("MM/yyyy"));
            p.conso    = r.consommation != null ? round2(r.consommation) : 0.0;
            p.distance = r.distance    != null ? round2(r.distance)    : 0.0;
            p.co2      = round2(p.conso * CO2_PER_LITER);
            p.cost     = round2(p.conso * COST_PER_LITER_TND);
            p.efficiency = p.distance > 0 ? round2((p.conso / p.distance) * 100.0) : 0.0;
            return p;
        }).collect(Collectors.toList());

        return buildChart(points);
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // STATISTIQUES AVANCÉES
    // ═══════════════════════════════════════════════════════════════════════════

    public FuelStatsDto getStats(Integer deviceId, LocalDateTime from, LocalDateTime to) {
        List<ArchiveFuelJ> daily   = ArchiveFuelJ.findByDeviceAndPeriod(deviceId, from, to);
        // archive_fuel_m utilisé uniquement via totalConsoByDeviceAndPeriod ci-dessous

        double avgDaily  = daily.stream().mapToDouble(r -> nvl(r.consommation)).average().orElse(0);
        double maxDaily  = daily.stream().mapToDouble(r -> nvl(r.consommation)).max().orElse(0);
        double minDaily  = daily.stream().mapToDouble(r -> nvl(r.consommation)).min().orElse(0);
        double avgDist   = daily.stream().mapToDouble(r -> nvl(r.distance)).average().orElse(0);
        double totalDist = daily.stream().mapToDouble(r -> nvl(r.distance)).sum();
        double avgSpeed  = daily.stream().mapToDouble(r -> nvl(r.vitesse)).average().orElse(0);
        double totalIdle = daily.stream().mapToDouble(r -> nvl(r.tempsArret)).sum();
        double totalConso = daily.stream().mapToDouble(r -> nvl(r.consommation)).sum();
        double eff = totalDist > 0 ? round2((totalConso / totalDist) * 100.0) : 0.0;

        // Variation vs mois précédent
        LocalDateTime prevFrom = from.minusMonths(1).withDayOfMonth(1).withHour(0).withMinute(0).withSecond(0);
        LocalDateTime prevEnd  = from.withDayOfMonth(1).withHour(0).withMinute(0).withSecond(0);
        Double curMonthConso  = ArchiveFuelM.totalConsoByDeviceAndPeriod(deviceId, from, to);
        Double prevMonthConso = ArchiveFuelM.totalConsoByDeviceAndPeriod(deviceId, prevFrom, prevEnd);

        FuelStatsDto dto = new FuelStatsDto();
        dto.deviceId             = deviceId;
        dto.avgDailyConsoL       = round2(avgDaily);
        dto.maxDailyConsoL       = round2(maxDaily);
        dto.minDailyConsoL       = round2(minDaily);
        dto.avgDailyDistanceKm   = round2(avgDist);
        dto.totalDistanceKm      = round2(totalDist);
        dto.avgEfficiencyL100km  = eff;
        dto.avgSpeedKmh          = round2(avgSpeed);
        dto.totalIdleMinutes     = round2(totalIdle);
        dto.variationVsPrevMonth = computeVariationPercent(curMonthConso, prevMonthConso);
        dto.totalAlerts          = countAlertsForDevice(deviceId, from, to);
        return dto;
    }

    public List<FuelStatsDto> getAllStats(LocalDateTime from, LocalDateTime to) {
        return FuelConsumption.findActiveDevices().stream()
                .map(d -> getStats(d, from, to))
                .collect(Collectors.toList());
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // ALERTES
    // ═══════════════════════════════════════════════════════════════════════════

    public List<FuelAlertDto> getActiveAlerts() {
        List<FuelAlertDto> alerts = new ArrayList<>();

        for (Integer deviceId : FuelConsumption.findActiveDevices()) {
            FuelConsumption latest = FuelConsumption.findLatestByDevice(deviceId);
            if (latest == null) continue;

            double consoL  = latest.consumptionLiters != null ? latest.consumptionLiters.doubleValue() : 0.0;

            // HIGH_CONSO — consommation > seuil
            if (consoL > ALERT_HIGH_CONSO_L) {
                FuelAlertDto a = new FuelAlertDto();
                a.deviceId = deviceId;
                a.date     = latest.id.date;
                a.type     = "HIGH_CONSO";
                a.value    = round2(consoL);
                a.message  = "Consommation anormalement élevée : " + round2(consoL) + " L le " + latest.id.date;
                a.severity = consoL > ALERT_HIGH_CONSO_L * 1.5 ? "CRITICAL" : "HIGH";
                alerts.add(a);
            }

            // LOW_EFFICIENCY (via archive_fuel_j latest)
            ArchiveFuelJ latestJ = ArchiveFuelJ.findByDevice(deviceId)
                    .stream().reduce((a2, b) -> b).orElse(null);
            if (latestJ != null && latestJ.consommation != null && latestJ.distance != null
                    && latestJ.distance > 0) {
                double eff = (latestJ.consommation / latestJ.distance) * 100.0;
                if (eff > ALERT_LOW_EFF_L100KM) {
                    FuelAlertDto a = new FuelAlertDto();
                    a.deviceId = deviceId;
                    a.date     = latestJ.date.toString();
                    a.type     = "LOW_EFFICIENCY";
                    a.value    = round2(eff);
                    a.message  = "Rendement faible : " + round2(eff) + " L/100km (seuil " + ALERT_LOW_EFF_L100KM + ")";
                    a.severity = eff > ALERT_LOW_EFF_L100KM * 1.3 ? "CRITICAL" : "HIGH";
                    alerts.add(a);
                }

                // EXCESSIVE_IDLE
                if (latestJ.tempsArret != null && latestJ.tempsArret > ALERT_IDLE_MIN) {
                    FuelAlertDto a = new FuelAlertDto();
                    a.deviceId = deviceId;
                    a.date     = latestJ.date.toString();
                    a.type     = "EXCESSIVE_IDLE";
                    a.value    = round2(latestJ.tempsArret);
                    a.message  = "Temps d'arrêt moteur excessif : " + round2(latestJ.tempsArret) + " min";
                    a.severity = "HIGH";
                    alerts.add(a);
                }
            }
        }
        return alerts;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // COMPARAISON PÉRIODES
    // ═══════════════════════════════════════════════════════════════════════════

    public FuelComparisonDto compareWithPreviousPeriod(
            Integer deviceId, LocalDateTime from, LocalDateTime to) {
        long duration = java.time.Duration.between(from, to).toDays();
        LocalDateTime prevFrom = from.minusDays(duration);

        double current  = FuelConsumption.findByDeviceAndPeriod(deviceId, from, to).stream()
                .mapToDouble(r -> r.consumptionLiters != null ? r.consumptionLiters.doubleValue() : 0.0)
                .sum();
        double previous = FuelConsumption.findByDeviceAndPeriod(deviceId, prevFrom, from).stream()
                .mapToDouble(r -> r.consumptionLiters != null ? r.consumptionLiters.doubleValue() : 0.0)
                .sum();

        FuelComparisonDto dto = new FuelComparisonDto();
        dto.currentPeriodConso  = round2(current);
        dto.previousPeriodConso = round2(previous);
        dto.variationPercent    = computeVariationPercent(current, previous);
        dto.trend = dto.variationPercent > 2 ? "UP"
                : dto.variationPercent < -2 ? "DOWN"
                : "STABLE";
        return dto;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // MAPPERS PRIVÉS
    // ═══════════════════════════════════════════════════════════════════════════

    private FuelLatestDto toLatestDto(FuelConsumption fc) {
        FuelLatestDto dto = new FuelLatestDto();
        dto.deviceId              = fc.id.deviceId;
        dto.date                  = fc.id.date;
        dto.fuelType              = fc.fuelType;
        dto.mileageKm             = fc.mileageKm;
        dto.consumptionLiters     = fc.consumptionLiters     != null ? fc.consumptionLiters.doubleValue()     : 0.0;
        dto.consumptionPercentage = fc.consumptionPercentage != null ? fc.consumptionPercentage.doubleValue() : 0.0;
        dto.tankCapacityLiters    = fc.tankCapacityLiters    != null ? fc.tankCapacityLiters.doubleValue()    : 0.0;
        dto.carbonKg              = fc.carbone               != null ? fc.carbone.doubleValue()               : 0.0;
        dto.costTnd               = fc.cost                  != null ? fc.cost.doubleValue()                  : 0.0;

        // Rendement : chercher dans archive_fuel_j même jour
        ArchiveFuelJ jRec = ArchiveFuelJ.findByDevice(fc.id.deviceId).stream()
                .filter(j -> j.date.toString().equals(fc.id.date))
                .findFirst().orElse(null);
        if (jRec != null && jRec.consommation != null && jRec.distance != null && jRec.distance > 0) {
            dto.efficiencyL100km = round2((jRec.consommation / jRec.distance) * 100.0);
        } else {
            dto.efficiencyL100km = 0.0;
        }

        dto.status = resolveStatus(dto);
        return dto;
    }

    private String resolveStatus(FuelLatestDto dto) {
        if (dto.consumptionLiters != null && dto.consumptionLiters > ALERT_HIGH_CONSO_L) return "HIGH_CONSO";
        if (dto.efficiencyL100km  != null && dto.efficiencyL100km  > ALERT_LOW_EFF_L100KM) return "LOW_EFFICIENCY";
        return "OK";
    }

    private ArchiveFuelDto toArchiveFuelDto(ArchiveFuel e) {
        ArchiveFuelDto dto = new ArchiveFuelDto();
        dto.id           = e.id;
        dto.date         = e.date;
        dto.idDevice     = e.idDevice;
        dto.lat          = e.lat;
        dto.lon          = e.lon;
        dto.temperature  = e.temperature;
        dto.vitesse      = e.vitesse;
        dto.consommation = e.consommation;
        dto.distance     = e.distance;
        dto.tempsArret   = e.tempsArret;
        return dto;
    }

    private ArchiveFuelHDto toArchiveFuelHDto(ArchiveFuelH e) {
        ArchiveFuelHDto dto = new ArchiveFuelHDto();
        dto.id           = e.id;
        dto.date         = e.date;
        dto.idDevice     = e.idDevice;
        dto.temperature  = e.temperature;
        dto.vitesse      = e.vitesse;
        dto.consommation = e.consommation;
        dto.distance     = e.distance;
        dto.tempsArret   = e.tempsArret;
        return dto;
    }

    private ArchiveFuelJDto toArchiveFuelJDto(ArchiveFuelJ e) {
        ArchiveFuelJDto dto = new ArchiveFuelJDto();
        dto.id           = e.id;
        dto.date         = e.date;
        dto.idDevice     = e.idDevice;
        dto.temperature  = e.temperature;
        dto.vitesse      = e.vitesse;
        dto.consommation = e.consommation;
        dto.distance     = e.distance;
        dto.tempsArret   = e.tempsArret;
        return dto;
    }

    private ArchiveFuelMDto toArchiveFuelMDto(ArchiveFuelM e) {
        ArchiveFuelMDto dto = new ArchiveFuelMDto();
        dto.id           = e.id;
        dto.date         = e.date;
        dto.idDevice     = e.idDevice;
        dto.temperature  = e.temperature;
        dto.vitesse      = e.vitesse;
        dto.consommation = e.consommation;
        dto.distance     = e.distance;
        dto.tempsArret   = e.tempsArret;
        return dto;
    }

    private FuelConsumptionDto toFuelConsumptionDto(FuelConsumption e) {
        FuelConsumptionDto dto = new FuelConsumptionDto();
        dto.date                  = e.id.date;
        dto.deviceId              = e.id.deviceId;
        dto.fuelType              = e.fuelType;
        dto.mileageKm             = e.mileageKm;
        dto.quantityAddedLiters   = e.quantityAddedLiters   != null ? e.quantityAddedLiters.doubleValue()   : 0.0;
        dto.consumptionLiters     = e.consumptionLiters     != null ? e.consumptionLiters.doubleValue()     : 0.0;
        dto.consumptionPercentage = e.consumptionPercentage != null ? e.consumptionPercentage.doubleValue() : 0.0;
        dto.tankCapacityLiters    = e.tankCapacityLiters    != null ? e.tankCapacityLiters.doubleValue()    : 0.0;
        dto.carbonKg              = e.carbone               != null ? e.carbone.doubleValue()               : 0.0;
        dto.costTnd               = e.cost                  != null ? e.cost.doubleValue()                  : 0.0;
        return dto;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // HELPERS
    // ═══════════════════════════════════════════════════════════════════════════

    private FuelChartDto buildChart(List<FuelChartPointDto> points) {
        double totalConso = points.stream().mapToDouble(p -> p.conso).sum();
        double totalDist  = points.stream().mapToDouble(p -> p.distance).sum();
        double totalCo2   = round2(totalConso * CO2_PER_LITER);
        double totalCost  = round2(totalConso * COST_PER_LITER_TND);
        double avgEff     = totalDist > 0 ? round2((totalConso / totalDist) * 100.0) : 0.0;

        FuelChartDto chart = new FuelChartDto();
        chart.points          = points;
        chart.totalConsoL     = round2(totalConso);
        chart.totalDistanceKm = round2(totalDist);
        chart.totalCo2        = totalCo2;
        chart.totalCost       = totalCost;
        chart.avgEfficiency   = avgEff;
        return chart;
    }

    private int countAlertsForDevice(Integer deviceId, LocalDateTime from, LocalDateTime to) {
        int count = 0;
        FuelConsumption latest = FuelConsumption.findLatestByDevice(deviceId);
        if (latest != null && latest.consumptionLiters != null
                && latest.consumptionLiters.doubleValue() > ALERT_HIGH_CONSO_L) count++;
        ArchiveFuelJ latestJ = ArchiveFuelJ.findByDevice(deviceId)
                .stream().reduce((a, b) -> b).orElse(null);
        if (latestJ != null) {
            if (latestJ.consommation != null && latestJ.distance != null && latestJ.distance > 0
                    && (latestJ.consommation / latestJ.distance) * 100.0 > ALERT_LOW_EFF_L100KM) count++;
            if (latestJ.tempsArret != null && latestJ.tempsArret > ALERT_IDLE_MIN) count++;
        }
        return count;
    }

    private String computeTrend(double current, double previous) {
        double pct  = computeVariationPercent(current, previous);
        String sign = pct >= 0 ? "+" : "";
        return sign + String.format("%.1f", pct) + "%";
    }

    private double computeVariationPercent(double current, double previous) {
        if (previous == 0) return 0.0;
        return ((current - previous) / previous) * 100.0;
    }

    private double nvl(Double v) { return v != null ? v : 0.0; }

    private double round2(double v) { return Math.round(v * 100.0) / 100.0; }
}
