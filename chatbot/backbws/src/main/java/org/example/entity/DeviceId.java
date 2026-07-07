package org.example.entity;   // ← était juste "entity" sans org.example

import java.io.Serializable;
import java.util.Objects;

public class DeviceId implements Serializable {

    private Integer id;
    private Integer adresse;

    public DeviceId() {}

    public DeviceId(Integer id, Integer adresse) {
        this.id = id;
        this.adresse = adresse;
    }

    public Integer getId()               { return id; }
    public void setId(Integer id)        { this.id = id; }
    public Integer getAdresse()          { return adresse; }
    public void setAdresse(Integer a)    { this.adresse = a; }

    @Override
    public boolean equals(Object o) {
        if (!(o instanceof DeviceId d)) return false;
        return Objects.equals(id, d.id) && Objects.equals(adresse, d.adresse);
    }

    @Override
    public int hashCode() { return Objects.hash(id, adresse); }
}