package org.example.service;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.persistence.EntityManager;
import org.example.dto.KpiDto;
import org.example.entity.Alert;
import org.example.entity.Device;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;

@ApplicationScoped
public class KpiService {

    @Inject
    EntityManager em;

    // Facteurs d'émission CO2 — Source : ADEME 2023 (kgCO2eq par unité consommée).
    // Valeurs alignées avec analytics.service.ts (Angular) pour cohérence cross-service.
    private static final double ELEC_CO2_FACTOR  = 0.233;  // kgCO2 / kWh  (réseau mixte EU/MENA)
    private static final double WATER_CO2_FACTOR = 0.376;  // kgCO2 / m³   (traitement + distribution)
    private static final double GAS_CO2_FACTOR   = 2.04;   // kgCO2 / m³   (combustion gaz naturel)
    private static final double FUEL_CO2_FACTOR  = 2.68;   // kgCO2 / L    (diesel — norme ADEME)

    public KpiDto getFullDashboard() {
        KpiDto dto    = new KpiDto();
        dto.summary   = getSummary();
        dto.chartData = getChartData(30);
        dto.deviceStats = getDeviceStats();
        dto.alerts    = getRecentAlerts(4);
        return dto;
    }

    public KpiDto.KpiSummary getSummary() {
        KpiDto.KpiSummary s = new KpiDto.KpiSummary();

        double elecKwh  = getElecSum(30);
        double waterL   = getWaterSum(30);
        double gasL     = getGasSum(30);
        double fuelL    = getFuelSum(30);

        s.electricityCo2 = elecKwh  * ELEC_CO2_FACTOR;
        s.waterCo2       = (waterL  / 1000.0) * WATER_CO2_FACTOR;
        s.gasCo2         = (gasL    / 1000.0) * GAS_CO2_FACTOR;
        s.fuelCo2        = fuelL    * FUEL_CO2_FACTOR;
        s.totalCo2       = s.electricityCo2 + s.waterCo2 + s.gasCo2 + s.fuelCo2;
        s.totalCost      = s.totalCo2 * 0.25;

        s.electricityTrend = trend(elecKwh, getElecSum(60, 30));
        s.waterTrend       = trend(waterL, getWaterSum(60, 30));
        s.gasTrend         = trend(gasL, getGasSum(60, 30));
        s.fuelTrend        = trend(fuelL, getFuelSum(60, 30));

        s.alertCount = countActiveAlerts();
        return s;
    }

    public List<KpiDto.ChartData> getChartData(int days) {
        List<KpiDto.ChartData> result = new ArrayList<>();

        for (int i = days - 1; i >= 0; i--) {
            LocalDateTime start = LocalDateTime.now().minusDays(i + 1).toLocalDate().atStartOfDay();
            LocalDateTime end   = LocalDateTime.now().minusDays(i).toLocalDate().atStartOfDay();

            KpiDto.ChartData p = new KpiDto.ChartData();
            p.label = start.format(DateTimeFormatter.ISO_LOCAL_DATE);
            p.electricity = elecBetween(start, end) * ELEC_CO2_FACTOR;
            p.water       = (waterBetween(start, end) / 1000.0) * WATER_CO2_FACTOR;
            p.fuel        = fuelBetween(start, end) * FUEL_CO2_FACTOR;
            result.add(p);
        }
        return result;
    }

    public KpiDto.DeviceStats getDeviceStats() {
        KpiDto.DeviceStats s = new KpiDto.DeviceStats();

        s.totalDevices = queryInt("SELECT COUNT(d) FROM Device d");

        s.activeDevices = queryInt(
            "SELECT COUNT(DISTINCT e.idDevice) FROM ArchiveEnP e WHERE e.date >= :p1",
            LocalDateTime.now().minusHours(1));

        s.totalSpaces  = queryInt("SELECT COUNT(e) FROM Espace e");
        s.activeSpaces = s.totalSpaces;

        s.alertDevices = queryInt(
            "SELECT COUNT(DISTINCT a.idDevice) FROM Alert a WHERE a.date >= :p1",
            LocalDateTime.now().minusDays(1));

        return s;
    }

    public List<KpiDto.AlertSummary> getRecentAlerts(int limit) {
        List<Alert> alerts = em.createQuery(
            "SELECT a FROM Alert a ORDER BY a.date DESC", Alert.class)
            .setMaxResults(Math.min(limit, 50))
            .getResultList();

        List<KpiDto.AlertSummary> list = new ArrayList<>();
        for (Alert a : alerts) {
            KpiDto.AlertSummary s = new KpiDto.AlertSummary();
            s.date       = a.date != null ? a.date.toString() : "";
            s.deviceName = resolveDeviceName(a.idDevice);
            s.message    = a.message != null ? a.message : a.type;
            s.severity   = severityFromType(a.type);
            list.add(s);
        }
        return list;
    }

    private double getElecSum(int days) {
        return queryDouble(
            "SELECT COALESCE(SUM(e.enL1 + e.enL2 + e.enL3), 0.0) FROM ArchiveEnP e WHERE e.date >= :p1",
            LocalDateTime.now().minusDays(days));
    }

    private double getElecSum(int daysAgo, int duration) {
        return queryDouble(
            "SELECT COALESCE(SUM(e.enL1 + e.enL2 + e.enL3), 0.0) FROM ArchiveEnP e WHERE e.date >= :p1 AND e.date < :p2",
            LocalDateTime.now().minusDays(daysAgo),
            LocalDateTime.now().minusDays(daysAgo - duration));
    }

    private double elecBetween(LocalDateTime s, LocalDateTime e) {
        return queryDouble(
            "SELECT COALESCE(SUM(e.enL1 + e.enL2 + e.enL3), 0.0) FROM ArchiveEnP e WHERE e.date >= :p1 AND e.date < :p2", s, e);
    }

    private double getWaterSum(int days) {
        return queryDouble(
            "SELECT COALESCE(SUM(w.wmIndex), 0.0) FROM ArchiveWm w WHERE w.id.date >= :p1",
            LocalDateTime.now().minusDays(days));
    }

    private double getWaterSum(int daysAgo, int duration) {
        return queryDouble(
            "SELECT COALESCE(SUM(w.wmIndex), 0.0) FROM ArchiveWm w WHERE w.id.date >= :p1 AND w.id.date < :p2",
            LocalDateTime.now().minusDays(daysAgo),
            LocalDateTime.now().minusDays(daysAgo - duration));
    }

    private double waterBetween(LocalDateTime s, LocalDateTime e) {
        return queryDouble(
            "SELECT COALESCE(SUM(w.wmIndex), 0.0) FROM ArchiveWm w WHERE w.id.date >= :p1 AND w.id.date < :p2", s, e);
    }

    private double getGasSum(int days) {
        return queryDouble(
            "SELECT COALESCE(SUM(g.index), 0.0) FROM ArchiveGm g WHERE g.id.date >= :p1",
            LocalDateTime.now().minusDays(days));
    }

    private double getGasSum(int daysAgo, int duration) {
        return queryDouble(
            "SELECT COALESCE(SUM(g.index), 0.0) FROM ArchiveGm g WHERE g.id.date >= :p1 AND g.id.date < :p2",
            LocalDateTime.now().minusDays(daysAgo),
            LocalDateTime.now().minusDays(daysAgo - duration));
    }

    private double getFuelSum(int days) {
        return queryDouble(
            "SELECT COALESCE(SUM(f.consommation), 0.0) FROM ArchiveFuel f WHERE f.date >= :p1",
            LocalDateTime.now().minusDays(days));
    }

    private double getFuelSum(int daysAgo, int duration) {
        return queryDouble(
            "SELECT COALESCE(SUM(f.consommation), 0.0) FROM ArchiveFuel f WHERE f.date >= :p1 AND f.date < :p2",
            LocalDateTime.now().minusDays(daysAgo),
            LocalDateTime.now().minusDays(daysAgo - duration));
    }

    private double fuelBetween(LocalDateTime s, LocalDateTime e) {
        return queryDouble(
            "SELECT COALESCE(SUM(f.consommation), 0.0) FROM ArchiveFuel f WHERE f.date >= :p1 AND f.date < :p2", s, e);
    }

    private double queryDouble(String jpql, LocalDateTime... params) {
        try {
            var q = em.createQuery(jpql);
            if (params.length > 0) q.setParameter("p1", params[0]);
            if (params.length > 1) q.setParameter("p2", params[1]);
            Object r = q.getSingleResult();
            return r != null ? ((Number) r).doubleValue() : 0.0;
        } catch (Exception ex) {
            return 0.0;
        }
    }

    private int queryInt(String jpql, LocalDateTime... params) {
        try {
            var q = em.createQuery(jpql);
            if (params.length > 0) q.setParameter("p1", params[0]);
            if (params.length > 1) q.setParameter("p2", params[1]);
            Object r = q.getSingleResult();
            return r != null ? ((Number) r).intValue() : 0;
        } catch (Exception ex) {
            return 0;
        }
    }

    private int countActiveAlerts() {
        return queryInt("SELECT COUNT(a) FROM Alert a");
    }

    private String resolveDeviceName(Integer id) {
        if (id == null) return "Inconnu";
        try {
            Device d = em.find(Device.class, id);
            return (d != null && d.getNom() != null) ? d.getNom() : "Device " + id;
        } catch (Exception e) {
            return "Device " + id;
        }
    }

    private String trend(double current, double previous) {
        if (previous <= 0) return "0.0%";
        double pct = ((current - previous) / previous) * 100.0;
        return String.format(java.util.Locale.US, "%+.1f%%", pct);
    }

    private String severityFromType(String type) {
        if (type == null) return "LOW";
        String t = type.toLowerCase();
        if (t.contains("excess") || t.contains("critical") || t.contains("danger"))
            return "CRITICAL";
        if (t.contains("high") || t.contains("warn") || t.contains("elev"))
            return "HIGH";
        return "LOW";
    }
}
