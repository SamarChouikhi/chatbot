package org.example.dto;

import java.time.LocalDateTime;

public class Alertdto {

    public LocalDateTime date;
    public Integer idDevice;
    public String type;
    public Double valeur;
    public Double diff;
    public Double valMin;
    public Double valMax;
    public Integer tempsInfraction;
    public String message;
    public String messageEn;
    public String recommendationEn;
    public String recommendationFr;
    public String from;

    public Alertdto() {}

    public Alertdto(org.example.entity.Alert a) {
        this.date = a.date;
        this.idDevice = a.idDevice;
        this.type = a.type;
        this.valeur = a.valeur;
        this.diff = a.diff;
        this.valMin = a.valMin;
        this.valMax = a.valMax;
        this.tempsInfraction = a.tempsInfraction;
        this.message = a.message;
        this.messageEn = a.messageEn;
        this.recommendationEn = a.recommendationEn;
        this.recommendationFr = a.recommendationFr;
        this.from = a.from;
    }
}