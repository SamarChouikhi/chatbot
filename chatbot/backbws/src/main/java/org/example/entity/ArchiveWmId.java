package org.example.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.time.LocalDateTime;
import java.util.Objects;

@Embeddable
public class ArchiveWmId implements Serializable {

    @Column(name = "id_device")
    public Integer idDevice;

    @Column(name = "date")
    public LocalDateTime date;

    public ArchiveWmId() {}

    public ArchiveWmId(Integer idDevice, LocalDateTime date) {
        this.idDevice = idDevice;
        this.date     = date;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof ArchiveWmId)) return false;
        ArchiveWmId that = (ArchiveWmId) o;
        return Objects.equals(idDevice, that.idDevice) && Objects.equals(date, that.date);
    }

    @Override
    public int hashCode() {
        return Objects.hash(idDevice, date);
    }
}
