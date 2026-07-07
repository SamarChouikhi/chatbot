package org.example.entity;

import java.io.Serializable;
import java.time.LocalDateTime;
import java.util.Objects;

public class Alertid implements Serializable {

    public LocalDateTime date;
    public Integer idDevice;
    public String type;

    public Alertid() {}

    public Alertid(LocalDateTime date, Integer idDevice, String type) {
        this.date = date;
        this.idDevice = idDevice;
        this.type = type;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof Alertid)) return false;
        Alertid that = (Alertid) o;
        return Objects.equals(date, that.date)
                && Objects.equals(idDevice, that.idDevice)
                && Objects.equals(type, that.type);
    }

    @Override
    public int hashCode() {
        return Objects.hash(date, idDevice, type);
    }
}