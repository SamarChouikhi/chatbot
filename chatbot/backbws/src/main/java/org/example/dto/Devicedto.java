package org.example.dto;

public class Devicedto {

    public Integer id;
    public Integer adresse;
    public String  nom;
    public String  description;
    public Integer type;
    public Integer id_espace;
    public String  geometry;
    public Integer max_uptime;
    public Integer id_ls;
    public Integer is_general_meter;
    public Double  last_saved_index;
    public String  login;

    public Devicedto() {}

    public Devicedto(org.example.entity.Device d) {
        this.id               = d.getId();
        this.adresse          = d.getAdresse();
        this.nom              = d.getNom();
        this.description      = d.getDescription();
        this.type             = d.getType();
        this.id_espace        = d.getIdEspace();
        this.geometry         = d.getGeometry();
        this.max_uptime       = d.getMaxUptime();
        this.id_ls            = d.getIdLs();
        this.is_general_meter = d.getIsGeneralMeter();
        this.last_saved_index = d.getLastSavedIndex();
        this.login            = d.getLogin();
    }
}