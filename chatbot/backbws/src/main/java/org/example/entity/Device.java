package org.example.entity;

import jakarta.persistence.*;

@Entity
@Table(name = "device")
@IdClass(DeviceId.class)
public class Device {

    @Id
    @Column(name = "id")
    private Integer id;

    @Id
    @Column(name = "adresse")
    private Integer adresse;

    @Column(name = "nom", length = 255)
    private String nom;

    @Column(name = "description", length = 255)
    private String description;

    @Column(name = "type")
    private Integer type;

    @Column(name = "id_espace")
    private Integer idEspace;

    @Column(name = "geometry", columnDefinition = "json")
    private String geometry;

    @Column(name = "max_uptime")
    private Integer maxUptime;

    @Column(name = "id_ls")
    private Integer idLs;

    @Column(name = "is_general_meter")
    private Integer isGeneralMeter;

    @Column(name = "last_saved_index")
    private Double lastSavedIndex;

    @Column(name = "login", length = 45)
    private String login;

    // ── Getters & Setters ─────────────────────────────────────────
    public Integer getId()                          { return id; }
    public void setId(Integer id)                   { this.id = id; }
    public Integer getAdresse()                     { return adresse; }
    public void setAdresse(Integer adresse)         { this.adresse = adresse; }
    public String getNom()                          { return nom; }
    public void setNom(String nom)                  { this.nom = nom; }
    public String getDescription()                  { return description; }
    public void setDescription(String description)  { this.description = description; }
    public Integer getType()                        { return type; }
    public void setType(Integer type)               { this.type = type; }
    public Integer getIdEspace()                    { return idEspace; }
    public void setIdEspace(Integer idEspace)       { this.idEspace = idEspace; }
    public String getGeometry()                     { return geometry; }
    public void setGeometry(String geometry)        { this.geometry = geometry; }
    public Integer getMaxUptime()                   { return maxUptime; }
    public void setMaxUptime(Integer maxUptime)     { this.maxUptime = maxUptime; }
    public Integer getIdLs()                        { return idLs; }
    public void setIdLs(Integer idLs)              { this.idLs = idLs; }
    public Integer getIsGeneralMeter()              { return isGeneralMeter; }
    public void setIsGeneralMeter(Integer v)        { this.isGeneralMeter = v; }
    public Double getLastSavedIndex()               { return lastSavedIndex; }
    public void setLastSavedIndex(Double v)         { this.lastSavedIndex = v; }
    public String getLogin()                        { return login; }
    public void setLogin(String login)              { this.login = login; }
}