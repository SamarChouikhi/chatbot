package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

/**
 * fuel_consumption — résumé journalier enrichi par véhicule
 * Colonnes : date (varchar PK), device_id (int PK), fuel_type, mileage_km,
 *            quantity_added_liters, consumption_liters, consumption_percentage,
 *            tank_capacity_liters, carbone, cost
 */
@Entity
@Table(name = "fuel_consumption")
public class FuelConsumption extends PanacheEntityBase {

    @EmbeddedId
    public FuelConsumptionId id;

    @Column(name = "fuel_type")
    public String fuelType;

    /** Kilométrage total (odomètre) en km */
    @Column(name = "mileage_km")
    public Integer mileageKm;

    /** Litres ajoutés (ravitaillement) */
    @Column(name = "quantity_added_liters")
    public BigDecimal quantityAddedLiters;

    /** Litres consommés ce jour */
    @Column(name = "consumption_liters")
    public BigDecimal consumptionLiters;

    /** % de la capacité cuve consommé */
    @Column(name = "consumption_percentage")
    public BigDecimal consumptionPercentage;

    /** Capacité du réservoir (L) */
    @Column(name = "tank_capacity_liters")
    public BigDecimal tankCapacityLiters;

    /** Émissions CO₂ calculées (kg) */
    @Column(name = "carbone")
    public BigDecimal carbone;

    /** Coût carburant (TND) */
    @Column(name = "cost")
    public BigDecimal cost;

    // ─── Queries ───────────────────────────────────────────────────────────────

    public static List<FuelConsumption> findByDevice(Integer deviceId) {
        return find("id.deviceId = ?1 ORDER BY id.date", deviceId).list();
    }

    public static List<FuelConsumption> findByDeviceAndPeriod(
            Integer deviceId, LocalDateTime from, LocalDateTime to) {
        String fromStr = from.toLocalDate().toString();
        String toStr   = to.toLocalDate().toString();
        return find("id.deviceId = ?1 AND id.date >= ?2 AND id.date <= ?3 ORDER BY id.date",
                deviceId, fromStr, toStr).list();
    }

    public static List<FuelConsumption> findAllByPeriod(
            LocalDateTime from, LocalDateTime to) {
        String fromStr = from.toLocalDate().toString();
        String toStr   = to.toLocalDate().toString();
        return find("id.date >= ?1 AND id.date <= ?2 ORDER BY id.deviceId, id.date",
                fromStr, toStr).list();
    }

    public static FuelConsumption findLatestByDevice(Integer deviceId) {
        return find("id.deviceId = ?1 ORDER BY id.date DESC", deviceId).firstResult();
    }

    public static List<Integer> findActiveDevices() {
        return getEntityManager()
                .createQuery(
                        "SELECT DISTINCT f.id.deviceId FROM FuelConsumption f ORDER BY f.id.deviceId",
                        Integer.class)
                .getResultList();
    }

    public static LocalDateTime findLatestDate() {
        String latest = (String) getEntityManager()
                .createQuery("SELECT MAX(f.id.date) FROM FuelConsumption f")
                .getSingleResult();
        if (latest == null) return null;
        try {
            return LocalDateTime.parse(latest + "T00:00:00");
        } catch (Exception e) {
            return null;
        }
    }
}
