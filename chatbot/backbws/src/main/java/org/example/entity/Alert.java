package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "alerts")
@IdClass(Alertid.class)          
public class Alert extends PanacheEntityBase {

    @Id
    @Column(name = "date", nullable = false)
    public LocalDateTime date;

    @Id
    @Column(name = "id_device", nullable = false)
    public Integer idDevice;

    @Id
    @Column(name = "type", length = 100, nullable = false)
    public String type;

    @Column(name = "valeur")
    public Double valeur;

    @Column(name = "diff")
    public Double diff;

    @Column(name = "val_min")
    public Double valMin;

    @Column(name = "val_max")
    public Double valMax;

    @Column(name = "temps_infraction")
    public Integer tempsInfraction;

    @Column(name = "message", columnDefinition = "TEXT")
    public String message;

    @Column(name = "message_en", columnDefinition = "TEXT")
    public String messageEn;

    @Column(name = "recommendation_en", columnDefinition = "TEXT")
    public String recommendationEn;

    @Column(name = "recommendation_fr", columnDefinition = "TEXT")
    public String recommendationFr;

    @Column(name = "from", length = 45)
    public String from;
}