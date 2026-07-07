package org.example.entity;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;

@Entity
@Table(name = "espace")
public class Espace extends PanacheEntityBase {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    public Integer id;

    @Column(name = "nom")
    public String nom;

    @Column(name = "type")
    public Integer type;

    @Column(name = "etat")
    public Integer etat;
}
