package org.example.dto;

import java.util.List;

public class KpiDto {

    public KpiSummary        summary;
    public List<ChartData>   chartData;
    public DeviceStats       deviceStats;
    public List<AlertSummary> alerts;

    public static class KpiSummary {
        public double electricityCo2;
        public double waterCo2;
        public double gasCo2;
        public double fuelCo2;
        public double totalCo2;
        public double totalCost;
        public String electricityTrend;
        public String waterTrend;
        public String gasTrend;
        public String fuelTrend;
        public int    alertCount;
    }

    public static class ChartData {
        public String label;
        public double electricity;
        public double water;
        public double fuel;
    }

    public static class DeviceStats {
        public int activeDevices;
        public int totalDevices;
        public int activeSpaces;
        public int totalSpaces;
        public int alertDevices;
    }

    public static class AlertSummary {
        public String date;
        public String deviceName;
        public String message;
        public String severity;
    }
}
