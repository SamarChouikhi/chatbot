package org.example.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

/**
 * Clé composite de fuel_consumption : (date VARCHAR, device_id INT)
 */
@Embeddable
public class FuelConsumptionId implements Serializable {

    @Column(name = "date")
    public String date;

    @Column(name = "device_id")
    public Integer deviceId;

    public FuelConsumptionId() {}

    public FuelConsumptionId(String date, Integer deviceId) {
        this.date     = date;
        this.deviceId = deviceId;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof FuelConsumptionId)) return false;
        FuelConsumptionId that = (FuelConsumptionId) o;
        return Objects.equals(date, that.date) && Objects.equals(deviceId, that.deviceId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(date, deviceId);
    }
}
